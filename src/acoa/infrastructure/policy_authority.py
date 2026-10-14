"""Current persisted authority for reserve/dispatch; trusted user adapters only, ADR-006."""

import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from typing import cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from acoa.config import Settings
from acoa.domain.authorization import AuthorizationGrant, SensitiveDataConsent, validate_scope
from acoa.domain.values import DomainError, require_identifier, require_text
from acoa.infrastructure.policy_codec import (
    decode_consent,
    decode_grant,
    decode_settings,
    encode_record,
    items,
    object_fields,
)
from acoa.infrastructure.postgres import (
    DatabaseBoundaryError,
    require_transaction,
    validate_application_connection,
)


@dataclass(frozen=True, slots=True)
class PolicyAuthority:
    settings: Settings = field(default_factory=Settings, repr=False)
    grant: AuthorizationGrant | None = field(default=None, repr=False)
    consents: tuple[SensitiveDataConsent, ...] = field(default=(), repr=False)
    timezone: str | None = None
    paused: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.settings, Settings) or not isinstance(self.paused, bool):
            raise DomainError("Authority requires validated settings and explicit pause state.")
        if self.grant is not None and not isinstance(self.grant, AuthorizationGrant):
            raise DomainError("Authority grants must be validated domain records.")
        validate_scope(self.consents, SensitiveDataConsent)
        if len({item.consent_id for item in self.consents}) != len(self.consents):
            raise DomainError("Only one current version per sensitive consent is permitted.")
        if self.timezone is not None:
            require_text(self.timezone)


def decode_authority(payload: object) -> PolicyAuthority:
    row = object_fields(payload)
    return PolicyAuthority(
        decode_settings(row["settings"]),
        decode_grant(row["grant"]),
        tuple(decode_consent(item) for item in items(row["consents"])),
        cast(str | None, row["timezone"]),
        cast(bool, row["paused"]),
    )


def approval_advances_only(previous: dict[str, object], current: dict[str, object]) -> bool:
    """Same content version may gain its first exact approval, never change an existing receipt."""
    before = previous.copy()
    after = current.copy()
    old_review = before.pop("approval")
    new_review = after.pop("approval")
    return before == after and (old_review is None or old_review == new_review)


class AuthorityStore:
    """Updates require an authenticated human/config adapter; not exposed to agents/providers."""

    def __init__(self, connection: Connection) -> None:
        validate_application_connection(connection)
        self.connection = connection

    def lock_current(self) -> tuple[int, PolicyAuthority]:
        require_transaction(self.connection)
        row = self.connection.execute(
            text("SELECT revision, payload FROM acoa.policy_authority WHERE singleton FOR UPDATE")
        ).one()
        try:
            return cast(int, row.revision), decode_authority(row.payload)
        except (KeyError, TypeError, ValueError, ArithmeticError):
            raise DatabaseBoundaryError(
                "Persisted policy authority is invalid; execution is blocked."
            ) from None

    def _validate_grant_history(self, authority: PolicyAuthority) -> None:
        """A previously revoked/newer version cannot be replaced by an older grant."""
        if authority.grant is not None:
            maximum: int | None = self.connection.execute(
                text("""
                SELECT max((payload->'grant'->>'version')::bigint)
                FROM acoa.policy_authority_versions WHERE payload->'grant'->>'grant_id' = :id
            """),
                {"id": str(authority.grant.grant_id)},
            ).scalar_one()
            if maximum is not None and authority.grant.version < maximum:
                raise DatabaseBoundaryError(
                    "An older grant version cannot replace authority history."
                )
            prior = self.connection.execute(
                text("""
                SELECT payload->'grant' FROM acoa.policy_authority_versions
                WHERE payload->'grant'->>'grant_id' = :id
                  AND (payload->'grant'->>'version')::bigint = :version
                ORDER BY revision DESC LIMIT 1
            """),
                {"id": str(authority.grant.grant_id), "version": authority.grant.version},
            ).scalar_one_or_none()
            if prior is not None and not approval_advances_only(
                object_fields(prior), json.loads(encode_record(asdict(authority.grant)))
            ):
                raise DatabaseBoundaryError(
                    "A grant version must retain its exact recorded content."
                )

    def _validate_consent_history(self, authority: PolicyAuthority) -> None:
        """Permit exact approval attachment, preserving prior consent versions and revocation."""
        for consent in authority.consents:
            rows: Sequence[object] = (
                self.connection.execute(
                    text("""
                SELECT item FROM acoa.policy_authority_versions v,
                    LATERAL jsonb_array_elements(v.payload->'consents') item
                WHERE item->>'consent_id' = :id
            """),
                    {"id": str(consent.consent_id)},
                )
                .scalars()
                .all()
            )
            encoded = json.loads(encode_record(asdict(consent)))
            for value in rows:
                row = object_fields(value)
                version = cast(int, row["version"])
                if version > consent.version or (
                    version == consent.version and not approval_advances_only(row, encoded)
                ):
                    raise DatabaseBoundaryError("Sensitive-consent history cannot be rolled back.")

    def replace(
        self,
        expected_revision: int,
        authority: PolicyAuthority,
        change_evidence_id: UUID,
    ) -> int:
        """Compare-and-swap a trusted human decision; never infer it from an agent plan."""
        require_identifier(change_evidence_id)
        if (
            isinstance(expected_revision, bool)
            or not isinstance(expected_revision, int)
            or expected_revision < 0
        ):
            raise DatabaseBoundaryError("Authority revision must be a nonnegative integer.")
        if not isinstance(authority, PolicyAuthority):
            raise DatabaseBoundaryError("A validated authority record is required.")
        revision, previous = self.lock_current()
        if revision != expected_revision:
            raise DatabaseBoundaryError("Authority changed; reload before applying this decision.")
        if (
            authority.timezone is not None
            and not self.connection.execute(
                text("SELECT EXISTS (SELECT 1 FROM pg_timezone_names WHERE name = :zone)"),
                {"zone": authority.timezone},
            ).scalar_one()
        ):
            raise DatabaseBoundaryError("The authority timezone is not supported by PostgreSQL.")
        if previous.settings.budget.currency != authority.settings.budget.currency:
            if self.connection.execute(
                text("SELECT EXISTS (SELECT 1 FROM acoa.budget_ledger)")
            ).scalar_one():
                raise DatabaseBoundaryError(
                    "Currency changes require a separate budget reconciliation."
                )
        self._validate_grant_history(authority)
        self._validate_consent_history(authority)
        encoded = encode_record(asdict(authority))
        self.connection.execute(
            text("""INSERT INTO acoa.policy_authority_versions
            (revision, payload, change_evidence_id)
            VALUES (:revision, CAST(:payload AS jsonb), :evidence)
        """),
            {"revision": revision + 1, "payload": encoded, "evidence": change_evidence_id},
        )
        self.connection.execute(
            text("""UPDATE acoa.policy_authority
            SET revision = :revision, payload = CAST(:payload AS jsonb),
                updated_at = clock_timestamp()
            WHERE singleton"""),
            {"revision": revision + 1, "payload": encoded},
        )
        return revision + 1
