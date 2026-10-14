"""Validated action requests shared by policy and prepared-action domain values."""

from dataclasses import dataclass, field
from uuid import UUID

from acoa.domain.authorization import ActionKind, Channel, DataCategory, validate_scope
from acoa.domain.reviews import content_digest
from acoa.domain.values import DomainError, require_identifier, require_sha256


@dataclass(frozen=True, slots=True)
class PolicyRequest:
    request_id: UUID = field(repr=False)
    action: ActionKind
    content_sha256: str = field(repr=False)
    channel: Channel | None = None
    recipient_id: UUID | None = field(default=None, repr=False)
    account_id: UUID | None = field(default=None, repr=False)
    data_categories: tuple[DataCategory, ...] = ()

    def __post_init__(self) -> None:
        require_identifier(self.request_id)
        require_sha256(self.content_sha256)
        if not isinstance(self.action, ActionKind):
            raise DomainError("Policy requests require a recognized action kind.")
        if self.channel is not None and not isinstance(self.channel, Channel):
            raise DomainError("A request channel must be explicit.")
        for identifier in (self.recipient_id, self.account_id):
            if identifier is not None:
                require_identifier(identifier)
        validate_scope(self.data_categories, DataCategory)


def request_binding_sha256(request: PolicyRequest) -> str:
    """Bind facts to exact content, action, channel, recipient, account and data scope."""
    return content_digest(
        {
            "request_id": str(request.request_id),
            "action": request.action.value,
            "content_sha256": request.content_sha256,
            "channel": request.channel.value if request.channel else None,
            "recipient_id": str(request.recipient_id) if request.recipient_id else None,
            "account_id": str(request.account_id) if request.account_id else None,
            "data_categories": [category.value for category in request.data_categories],
        }
    )
