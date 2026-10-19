"""Pinned HTTPS adapter for the public Arbeitnow job-board API."""

import http.client
import json
import socket
import ssl
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs, quote, urljoin, urlsplit
from uuid import NAMESPACE_URL, uuid5

from acoa.application.discovery import (
    EndpointResolver,
    ResolvedEndpoint,
    SourceTransport,
    TransportDiscoveryResponse,
    TransportFetchResponse,
    TransportResource,
)
from acoa.domain.authorization import DataCategory
from acoa.domain.discovery import (
    DiscoveredResource,
    DiscoveryQuery,
    SourceAccessPermit,
    SourceAccessStatus,
    SourceKind,
    SourcePolicy,
    SourceResourceKind,
)
from acoa.domain.values import DomainError

ARBEITNOW_HOST = "www.arbeitnow.com"
ARBEITNOW_ENTRYPOINT = f"https://{ARBEITNOW_HOST}/api/job-board-api"
ARBEITNOW_SOURCE_ID = uuid5(NAMESPACE_URL, "acoa:source:arbeitnow-job-board-api")
ARBEITNOW_POLICY_VERSION = "arbeitnow-public-api/2026-10-20"
_POLICY_OBSERVED_AT = datetime(2026, 10, 19, 21, tzinfo=UTC)
_POLICY_VALID_UNTIL = datetime(2026, 11, 18, 21, tzinfo=UTC)
_MAX_PAGE = 100
_REDIRECT_STATUSES = frozenset((301, 302, 303, 307, 308))


@dataclass(frozen=True, slots=True)
class _HttpResponse:
    status: int
    body: bytes
    media_type: str | None
    declared_length: int | None
    location: str | None


class PublicDnsResolver(EndpointResolver):
    """Resolve TCP endpoints; DiscoveryService rejects every non-public address."""

    def resolve(self, host: str, port: int) -> tuple[str, ...]:
        records = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        return tuple(sorted({str(record[4][0]) for record in records}))


class ArbeitnowTransport(SourceTransport):
    """Read Arbeitnow through address-pinned TLS without automatic redirects."""

    def __init__(self, max_response_bytes: int, timeout_seconds: float = 15.0) -> None:
        if (
            isinstance(max_response_bytes, bool)
            or not isinstance(max_response_bytes, int)
            or max_response_bytes < 1
        ):
            raise DomainError("Arbeitnow transport requires a positive response bound.")
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or timeout_seconds <= 0
        ):
            raise DomainError("Arbeitnow transport requires a positive timeout.")
        self.max_response_bytes = max_response_bytes
        self.timeout_seconds = float(timeout_seconds)

    def discover(
        self,
        endpoint: ResolvedEndpoint,
        query: DiscoveryQuery,
        cursor: str | None,
    ) -> TransportDiscoveryResponse:
        page = _parse_page(cursor)
        response = self._request(endpoint, f"?page={page}")
        redirect = _redirect_response(response, endpoint.url)
        if redirect is not None:
            return TransportDiscoveryResponse(
                status=SourceAccessStatus.SUCCEEDED,
                redirect_url=redirect,
            )
        status = _access_status(response.status)
        if status is not SourceAccessStatus.SUCCEEDED:
            return TransportDiscoveryResponse(status=status)
        if response.media_type != "application/json":
            return TransportDiscoveryResponse(status=SourceAccessStatus.INVALID_RESPONSE)
        payload = _decode_payload(response.body)
        if payload is None:
            return TransportDiscoveryResponse(status=SourceAccessStatus.INVALID_RESPONSE)
        resources = _matching_resources(payload, query)
        if resources is None:
            return TransportDiscoveryResponse(status=SourceAccessStatus.INVALID_RESPONSE)
        return TransportDiscoveryResponse(
            status=SourceAccessStatus.SUCCEEDED,
            resources=resources,
            next_cursor=_next_cursor(payload, page),
        )

    def fetch(
        self, endpoint: ResolvedEndpoint, resource: DiscoveredResource
    ) -> TransportFetchResponse:
        response = self._request(endpoint, "")
        redirect = _redirect_response(response, endpoint.url)
        if redirect is not None:
            return TransportFetchResponse(
                status=SourceAccessStatus.SUCCEEDED,
                redirect_url=redirect,
            )
        status = _access_status(response.status)
        if status is not SourceAccessStatus.SUCCEEDED:
            return TransportFetchResponse(status=status)
        return TransportFetchResponse(
            status=status,
            body=response.body,
            media_type=response.media_type,
            declared_length=response.declared_length,
        )

    def _request(self, endpoint: ResolvedEndpoint, query_suffix: str) -> _HttpResponse:
        _require_arbeitnow_endpoint(endpoint)
        target = _request_target(endpoint.url, query_suffix)
        last_error: OSError | None = None
        for address in endpoint.addresses:
            try:
                return self._request_address(endpoint.host, address, target)
            except TimeoutError:
                last_error = TimeoutError("Arbeitnow request timed out.")
            except http.client.HTTPException:
                last_error = OSError("Arbeitnow returned an incomplete HTTP response.")
            except OSError as error:
                last_error = error
        if last_error is None:
            raise OSError("Arbeitnow endpoint has no pinned address.")
        raise last_error

    def _request_address(self, host: str, address: str, target: str) -> _HttpResponse:
        raw_socket = socket.create_connection((address, 443), timeout=self.timeout_seconds)
        try:
            context = ssl.create_default_context()
            with context.wrap_socket(raw_socket, server_hostname=host) as tls_socket:
                request = (
                    f"GET {target} HTTP/1.1\r\n"
                    f"Host: {host}\r\n"
                    "Accept: application/json, text/html;q=0.9\r\n"
                    "Accept-Encoding: identity\r\n"
                    "User-Agent: ACOA/0.1 (+local single-user job discovery)\r\n"
                    "Connection: close\r\n\r\n"
                )
                tls_socket.sendall(request.encode("ascii"))
                response = http.client.HTTPResponse(tls_socket)
                response.begin()
                return self._read_response(response)
        finally:
            raw_socket.close()

    def _read_response(self, response: http.client.HTTPResponse) -> _HttpResponse:
        declared_length = _declared_length(response.getheader("Content-Length"))
        if declared_length is not None and declared_length > self.max_response_bytes:
            raise OSError("Arbeitnow response exceeds its configured byte bound.")
        if response.getheader("Content-Encoding", "identity").casefold() != "identity":
            raise OSError("Arbeitnow returned an unsupported content encoding.")
        body = response.read(self.max_response_bytes + 1)
        if len(body) > self.max_response_bytes:
            raise OSError("Arbeitnow response exceeds its configured byte bound.")
        return _HttpResponse(
            status=response.status,
            body=body,
            media_type=_base_media_type(response.getheader("Content-Type")),
            declared_length=declared_length,
            location=response.getheader("Location"),
        )


def arbeitnow_source_policy() -> SourcePolicy:
    """Return the reviewed finite policy for the public Arbeitnow API."""

    return SourcePolicy(
        source_id=ARBEITNOW_SOURCE_ID,
        policy_version=ARBEITNOW_POLICY_VERSION,
        name="Arbeitnow public job-board API",
        kind=SourceKind.OFFICIAL_API,
        entrypoint_url=ARBEITNOW_ENTRYPOINT,
        allowed_hosts=(ARBEITNOW_HOST,),
        allowed_media_types=("application/json", "text/html"),
        allowed_data_categories=(DataCategory.PROFESSIONAL_PROFILE,),
        terms_reference="https://www.arbeitnow.com/terms",
        license_reference="https://blog.arbeitnow.com/blog/job-board-api",
        observed_at=_POLICY_OBSERVED_AT,
        valid_until=_POLICY_VALID_UNTIL,
        access_allowed=True,
        max_response_bytes=4_194_304,
        max_redirects=2,
        max_batch_results=100,
        snapshot_ttl_seconds=86_400,
    )


def arbeitnow_access_permit() -> SourceAccessPermit:
    """Return the finite read-only access decision bound to the reviewed policy."""

    return SourceAccessPermit(
        decision_id=uuid5(NAMESPACE_URL, "acoa:source-permit:arbeitnow-public-api/2026-10-20"),
        source_id=ARBEITNOW_SOURCE_ID,
        policy_version=ARBEITNOW_POLICY_VERSION,
        evaluated_at=_POLICY_OBSERVED_AT,
        expires_at=_POLICY_VALID_UNTIL,
        allowed=True,
    )


def _parse_page(cursor: str | None) -> int:
    if cursor is None:
        return 1
    if not cursor.isascii() or not cursor.isdecimal():
        raise DomainError("An Arbeitnow cursor must be a decimal page number.")
    page = int(cursor)
    if not 1 <= page <= _MAX_PAGE:
        raise DomainError("An Arbeitnow cursor exceeds the configured page bound.")
    return page


def _require_arbeitnow_endpoint(endpoint: ResolvedEndpoint) -> None:
    if not isinstance(endpoint, ResolvedEndpoint):
        raise DomainError("Arbeitnow transport requires a resolved endpoint.")
    try:
        parsed = urlsplit(endpoint.url)
        port = parsed.port
    except (TypeError, ValueError) as error:
        raise DomainError("Arbeitnow transport requires a canonical endpoint URL.") from error
    if (
        endpoint.host != ARBEITNOW_HOST
        or parsed.scheme != "https"
        or parsed.hostname != ARBEITNOW_HOST
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or parsed.query
        or parsed.fragment
        or not isinstance(endpoint.addresses, tuple)
        or not endpoint.addresses
        or any(not isinstance(address, str) or not address for address in endpoint.addresses)
    ):
        raise DomainError("Arbeitnow transport rejected an endpoint outside its fixed boundary.")


def _request_target(url: str, query_suffix: str) -> str:
    parsed = urlsplit(url)
    path = quote(parsed.path or "/", safe="/%:@-._~!$&'()*+,;=")
    target = f"{path}{query_suffix}"
    try:
        target.encode("ascii")
    except UnicodeEncodeError as error:
        raise DomainError("An Arbeitnow request target must be ASCII encodable.") from error
    return target


def _declared_length(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        length = int(value)
    except ValueError as error:
        raise OSError("Arbeitnow returned an invalid content length.") from error
    if length < 0:
        raise OSError("Arbeitnow returned an invalid content length.")
    return length


def _base_media_type(value: str | None) -> str | None:
    if value is None:
        return None
    return value.partition(";")[0].strip().casefold() or None


def _redirect_response(response: _HttpResponse, base_url: str) -> str | None:
    if response.status not in _REDIRECT_STATUSES:
        return None
    if response.location is None:
        raise OSError("Arbeitnow returned a redirect without a location.")
    return urljoin(base_url, response.location)


def _access_status(status: int) -> SourceAccessStatus:
    if status == 200:
        return SourceAccessStatus.SUCCEEDED
    if status == 404:
        return SourceAccessStatus.NOT_FOUND
    if status in (401, 403):
        return SourceAccessStatus.ACCESS_CHALLENGE
    if status in (408, 504):
        return SourceAccessStatus.TIMEOUT
    if status == 429 or 500 <= status <= 599:
        return SourceAccessStatus.UNAVAILABLE
    return SourceAccessStatus.INVALID_RESPONSE


def _decode_payload(body: bytes) -> dict[str, Any] | None:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _matching_resources(
    payload: dict[str, Any], query: DiscoveryQuery
) -> tuple[TransportResource, ...] | None:
    rows = payload.get("data")
    if not isinstance(rows, list):
        return None
    terms = tuple(term for term in query.text.casefold().split() if term)
    resources: list[TransportResource] = []
    for row in rows:
        resource = _resource(row, terms)
        if resource is not None:
            resources.append(resource)
        if len(resources) == query.max_results:
            break
    return tuple(resources)


def _resource(row: object, terms: tuple[str, ...]) -> TransportResource | None:
    if not isinstance(row, dict):
        return None
    slug = row.get("slug")
    url = row.get("url")
    if (
        not isinstance(slug, str)
        or not slug
        or slug != slug.strip()
        or len(slug) > 2048
        or not isinstance(url, str)
        or not _valid_resource_url(url)
    ):
        return None
    searchable = _searchable_text(row)
    if terms and not all(term in searchable for term in terms):
        return None
    return TransportResource(
        kind=SourceResourceKind.OPPORTUNITY,
        external_id=slug,
        url=url,
    )


def _valid_resource_url(url: str) -> bool:
    if (
        not url
        or len(url) > 4096
        or url != url.strip()
        or any(ord(character) < 32 or character == "\\" for character in url)
    ):
        return False
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and parsed.hostname == ARBEITNOW_HOST
        and parsed.username is None
        and parsed.password is None
        and port in (None, 443)
        and bool(parsed.path)
        and not parsed.query
        and not parsed.fragment
    )


def _searchable_text(row: dict[str, Any]) -> str:
    values: list[str] = []
    for key in ("title", "company_name", "location"):
        value = row.get(key)
        if isinstance(value, str):
            values.append(value)
    for key in ("tags", "job_types"):
        value = row.get(key)
        if isinstance(value, list):
            values.extend(item for item in value if isinstance(item, str))
    if row.get("remote") is True:
        values.append("remote")
    return " ".join(values).casefold()


def _next_cursor(payload: dict[str, Any], page: int) -> str | None:
    meta = payload.get("meta")
    if not isinstance(meta, dict):
        return None
    current_page = meta.get("current_page")
    if not isinstance(current_page, int) or isinstance(current_page, bool) or current_page != page:
        return None
    links = payload.get("links")
    if not isinstance(links, dict):
        return None
    next_url = links.get("next")
    if next_url is None:
        return None
    if not isinstance(next_url, str):
        return None
    parsed = urlsplit(next_url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != ARBEITNOW_HOST
        or parsed.path != "/api/job-board-api"
        or parsed.fragment
    ):
        return None
    try:
        values = parse_qs(parsed.query, strict_parsing=True)
    except ValueError:
        return None
    page_values = values.get("page")
    if set(values) != {"page"} or page_values is None or len(page_values) != 1:
        return None
    next_page = page_values[0]
    if not next_page.isascii() or not next_page.isdecimal():
        return None
    parsed_page = int(next_page)
    if parsed_page != current_page + 1 or parsed_page > _MAX_PAGE:
        return None
    return next_page
