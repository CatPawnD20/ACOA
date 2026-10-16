"""Task-scoped browser-worker authority and network resolution guards; EP-08.02."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from ipaddress import ip_address
from typing import Protocol
from urllib.parse import urlsplit
from uuid import UUID

from acoa.domain.browser import BrowserCapability, BrowserPermit, page_origin
from acoa.domain.values import DomainError, require_identifier, require_timestamp


class BrowserWorkerOperation(StrEnum):
    INSPECT = "inspect"
    FILL_DRAFT = "fill_draft"
    UPLOAD_DOCUMENT = "upload_document"


_OPERATION_CAPABILITIES = {
    BrowserWorkerOperation.INSPECT: (BrowserCapability.VISIT, BrowserCapability.READ_PAGE),
    BrowserWorkerOperation.FILL_DRAFT: (BrowserCapability.FILL_DRAFT,),
    BrowserWorkerOperation.UPLOAD_DOCUMENT: (BrowserCapability.UPLOAD_DOCUMENT,),
}


class BrowserEndpointResolver(Protocol):
    """Resolve a DNS host; the transport must connect only to the returned addresses."""

    def resolve(self, host: str, port: int) -> tuple[str, ...]: ...


@dataclass(frozen=True, slots=True)
class BrowserWorkerInvocation:
    invocation_id: UUID = field(repr=False)
    permit: BrowserPermit = field(repr=False)
    operation: BrowserWorkerOperation
    url: str = field(repr=False)
    issued_at: datetime

    def __post_init__(self) -> None:
        require_identifier(self.invocation_id)
        if not isinstance(self.permit, BrowserPermit):
            raise DomainError("A browser-worker invocation requires validated authority.")
        if not isinstance(self.operation, BrowserWorkerOperation):
            raise DomainError("A browser-worker invocation requires an allowed operation.")
        require_timestamp(self.issued_at)
        if self.issued_at >= self.permit.expires_at:
            raise DomainError("A browser-worker invocation requires current authority.")
        required = _OPERATION_CAPABILITIES[self.operation]
        if not set(required) <= set(self.permit.capabilities):
            raise DomainError("A browser-worker operation exceeds its task authority.")
        if page_origin(self.url) != self.permit.allowed_origin:
            raise DomainError("A browser-worker invocation cannot leave its permitted origin.")


@dataclass(frozen=True, slots=True)
class BrowserNetworkTarget:
    url: str = field(repr=False)
    host: str
    port: int
    addresses: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.addresses, tuple) or not self.addresses:
            raise DomainError("Browser DNS resolution requires immutable public addresses.")


class BrowserNetworkGuard:
    """Authorize exact-origin navigation and pin each hop to public DNS answers."""

    def __init__(self, resolver: BrowserEndpointResolver, max_redirects: int = 5) -> None:
        if (
            isinstance(max_redirects, bool)
            or not isinstance(max_redirects, int)
            or max_redirects < 0
        ):
            raise DomainError("The browser redirect bound must be a nonnegative integer.")
        self.resolver = resolver
        self.max_redirects = max_redirects

    def authorize(
        self,
        invocation: BrowserWorkerInvocation,
        url: str,
        redirect_count: int,
        now: datetime,
    ) -> BrowserNetworkTarget:
        require_timestamp(now)
        if (
            not isinstance(invocation, BrowserWorkerInvocation)
            or now >= invocation.permit.expires_at
        ):
            raise DomainError("Browser network access requires current task authority.")
        if (
            isinstance(redirect_count, bool)
            or not isinstance(redirect_count, int)
            or redirect_count < 0
            or redirect_count > self.max_redirects
        ):
            raise DomainError("Browser navigation exceeded its redirect bound.")
        canonical_url, host, port = self._canonical_url(url, invocation.permit.allowed_origin)
        addresses = self.resolver.resolve(host, port)
        if not isinstance(addresses, tuple) or not addresses:
            raise DomainError("Browser DNS resolution requires immutable public addresses.")
        canonical_addresses = tuple(sorted(set(addresses)))
        if len(canonical_addresses) != len(addresses):
            raise DomainError("Browser DNS resolution must not repeat addresses.")
        for address in canonical_addresses:
            try:
                resolved = ip_address(address)
            except ValueError as error:
                raise DomainError("Browser DNS resolution returned an invalid address.") from error
            if not resolved.is_global:
                raise DomainError("Browser network access resolved to a non-public address.")
        return BrowserNetworkTarget(canonical_url, host, port, canonical_addresses)

    @staticmethod
    def _canonical_url(url: str, allowed_origin: str) -> tuple[str, str, int]:
        if (
            not isinstance(url, str)
            or not url
            or url != url.strip()
            or len(url) > 4096
            or any(ord(character) < 32 or character == "\\" for character in url)
        ):
            raise DomainError("A browser URL must be bounded canonical text.")
        try:
            parsed = urlsplit(url)
            host = parsed.hostname
            port = parsed.port
        except ValueError as error:
            raise DomainError("A browser URL is malformed.") from error
        if (
            parsed.scheme != "https"
            or host is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
        ):
            raise DomainError("Browser navigation requires HTTPS without credentials or fragments.")
        try:
            canonical_host = host.encode("idna").decode("ascii").lower().rstrip(".")
            ip_address(canonical_host)
        except UnicodeError as error:
            raise DomainError("A browser URL host is malformed.") from error
        except ValueError:
            pass
        else:
            raise DomainError("Browser URLs must not use direct IP literals.")
        network_port = port or 443
        origin = f"https://{canonical_host}{f':{network_port}' if network_port != 443 else ''}"
        if origin != allowed_origin:
            raise DomainError("Browser navigation cannot leave the permitted origin.")
        path = parsed.path or "/"
        canonical = f"{origin}{path}{f'?{parsed.query}' if parsed.query else ''}"
        if canonical != url:
            raise DomainError("Browser navigation requires a canonical URL.")
        return canonical, canonical_host, network_port
