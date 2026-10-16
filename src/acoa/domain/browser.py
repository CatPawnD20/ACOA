"""Browser interaction contracts with explicit capabilities and handoff states; EP-08.01."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from ipaddress import ip_address
from urllib.parse import urlsplit
from uuid import UUID

from acoa.domain.authorization import validate_scope
from acoa.domain.values import (
    DomainError,
    require_identifier,
    require_sha256,
    require_text,
    require_timestamp,
)


class BrowserCapability(StrEnum):
    VISIT = "visit"
    READ_PAGE = "read_page"
    FILL_DRAFT = "fill_draft"
    UPLOAD_DOCUMENT = "upload_document"
    PREPARE_SUBMISSION = "prepare_submission"


class BrowserFieldKind(StrEnum):
    TEXT = "text"
    EMAIL = "email"
    PHONE = "phone"
    URL = "url"
    TEXTAREA = "textarea"
    SELECT = "select"
    CHECKBOX = "checkbox"
    RADIO = "radio"
    FILE = "file"
    UNKNOWN = "unknown"


class BrowserFieldPurpose(StrEnum):
    FULL_NAME = "full_name"
    EMAIL = "email"
    PHONE = "phone"
    PROFESSIONAL_URL = "professional_url"
    COVER_LETTER = "cover_letter"
    RESUME_UPLOAD = "resume_upload"
    WORK_AUTHORIZATION = "work_authorization"
    OTHER = "other"
    UNKNOWN = "unknown"


class BrowserObstacle(StrEnum):
    CAPTCHA = "captcha"
    MFA = "mfa"
    AUTHENTICATION_REQUIRED = "authentication_required"
    ACCESS_DENIED = "access_denied"


class BrowserHandoffReason(StrEnum):
    ACCESS_CHALLENGE = "access_challenge"
    UNKNOWN_REQUIRED_FIELD = "unknown_required_field"
    REQUIRED_VALUE_MISSING = "required_value_missing"


def public_https_origin(value: str) -> str:
    """Accept a canonical HTTPS DNS origin, excluding credentials, paths and IP literals."""
    require_text(value)
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
        or parsed.hostname is None
        or "." not in parsed.hostname
        or parsed.hostname.replace(".", "").isdigit()
    ):
        raise DomainError("Browser authority requires a canonical public HTTPS DNS origin.")
    try:
        port = parsed.port
    except ValueError:
        raise DomainError("Browser authority contains an invalid port.") from None
    try:
        host = parsed.hostname.encode("idna").decode("ascii").lower()
    except UnicodeError:
        raise DomainError("Browser authority contains an invalid DNS host.") from None
    if host.endswith(".") or host == "localhost" or host.endswith(".localhost"):
        raise DomainError("Browser authority cannot target a local host.")
    try:
        ip_address(host)
    except ValueError:
        pass
    else:
        raise DomainError("Browser authority cannot target an IP literal.")
    return f"https://{host}{f':{port}' if port not in (None, 443) else ''}"


def page_origin(value: str) -> str:
    require_text(value)
    parsed = urlsplit(value)
    if (
        parsed.hostname is None
        or parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise DomainError("Browser pages require an HTTPS URL.")
    try:
        port = parsed.port
    except ValueError:
        raise DomainError("Browser page URL contains an invalid port.") from None
    try:
        host = parsed.hostname.encode("idna").decode("ascii").lower()
    except UnicodeError:
        raise DomainError("Browser page URL contains an invalid DNS host.") from None
    return f"https://{host}{f':{port}' if port not in (None, 443) else ''}"


@dataclass(frozen=True, slots=True)
class BrowserPermit:
    permit_id: UUID = field(repr=False)
    task_id: UUID = field(repr=False)
    application_id: UUID = field(repr=False)
    allowed_origin: str
    capabilities: tuple[BrowserCapability, ...]
    expires_at: datetime

    def __post_init__(self) -> None:
        for identifier in (self.permit_id, self.task_id, self.application_id):
            require_identifier(identifier)
        if self.allowed_origin != public_https_origin(self.allowed_origin):
            raise DomainError("Browser authority must use its canonical origin.")
        validate_scope(self.capabilities, BrowserCapability)
        if not self.capabilities:
            raise DomainError("Browser authority requires explicit capabilities.")
        require_timestamp(self.expires_at)


@dataclass(frozen=True, slots=True)
class BrowserField:
    field_id: UUID = field(repr=False)
    kind: BrowserFieldKind
    purpose: BrowserFieldPurpose
    required: bool
    accepted_media_types: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_identifier(self.field_id)
        if not isinstance(self.kind, BrowserFieldKind) or not isinstance(
            self.purpose, BrowserFieldPurpose
        ):
            raise DomainError("Browser fields require explicit kind and purpose values.")
        if not isinstance(self.required, bool):
            raise DomainError("Browser field required state must be explicit.")
        if not isinstance(self.accepted_media_types, tuple):
            raise DomainError("Browser file types must be an immutable tuple.")
        for media_type in self.accepted_media_types:
            require_text(media_type)
            if media_type != media_type.lower() or any(
                character.isspace() for character in media_type
            ):
                raise DomainError("Browser file media types must be normalized labels.")
        if len(set(self.accepted_media_types)) != len(self.accepted_media_types):
            raise DomainError("Browser file media types cannot repeat.")
        if self.kind is not BrowserFieldKind.FILE and self.accepted_media_types:
            raise DomainError("Only file fields may declare accepted media types.")


@dataclass(frozen=True, slots=True)
class BrowserPageObservation:
    observation_id: UUID = field(repr=False)
    permit_id: UUID = field(repr=False)
    url: str = field(repr=False)
    page_sha256: str = field(repr=False)
    fields: tuple[BrowserField, ...]
    obstacles: tuple[BrowserObstacle, ...]
    observed_at: datetime

    def __post_init__(self) -> None:
        for identifier in (self.observation_id, self.permit_id):
            require_identifier(identifier)
        page_origin(self.url)
        require_sha256(self.page_sha256)
        validate_scope(self.fields, BrowserField)
        if len({item.field_id for item in self.fields}) != len(self.fields):
            raise DomainError("A browser observation cannot repeat a field identity.")
        validate_scope(self.obstacles, BrowserObstacle)
        require_timestamp(self.observed_at)


@dataclass(frozen=True, slots=True)
class BrowserFieldValue:
    field_id: UUID = field(repr=False)
    purpose: BrowserFieldPurpose
    value: str = field(repr=False)
    value_sha256: str = field(repr=False)

    def __post_init__(self) -> None:
        require_identifier(self.field_id)
        if not isinstance(self.purpose, BrowserFieldPurpose):
            raise DomainError("Browser field values require an explicit purpose.")
        require_text(self.value)
        require_sha256(self.value_sha256)


@dataclass(frozen=True, slots=True)
class BrowserUploadReceipt:
    observation_id: UUID = field(repr=False)
    field_id: UUID = field(repr=False)
    artifact_id: UUID = field(repr=False)
    artifact_version: int
    content_sha256: str = field(repr=False)
    uploaded_at: datetime

    def __post_init__(self) -> None:
        for identifier in (self.observation_id, self.field_id, self.artifact_id):
            require_identifier(identifier)
        if (
            isinstance(self.artifact_version, bool)
            or not isinstance(self.artifact_version, int)
            or self.artifact_version < 1
        ):
            raise DomainError("Browser upload receipts require a positive artifact version.")
        require_sha256(self.content_sha256)
        require_timestamp(self.uploaded_at)


@dataclass(frozen=True, slots=True)
class BrowserHandoff:
    reason: BrowserHandoffReason
    observation_id: UUID = field(repr=False)
    field_ids: tuple[UUID, ...] = field(default=(), repr=False)
    obstacles: tuple[BrowserObstacle, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.reason, BrowserHandoffReason):
            raise DomainError("Browser handoff requires an explicit reason.")
        require_identifier(self.observation_id)
        validate_scope(self.field_ids, UUID)
        validate_scope(self.obstacles, BrowserObstacle)
