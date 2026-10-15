"""Current provider/data scopes; only trusted authenticated user/config adapters may update."""

from dataclasses import asdict
from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from acoa.domain.authorization import DataCategory
from acoa.domain.model_privacy import DataSensitivity, ProviderPermission
from acoa.domain.values import require_identifier
from acoa.infrastructure.policy_authority import AuthorityStore
from acoa.infrastructure.policy_codec import (
    encode_record,
    identifier,
    items,
    object_fields,
    text_value,
    timestamp,
)
from acoa.infrastructure.postgres import (
    DatabaseBoundaryError,
    require_transaction,
    validate_application_connection,
)


def decode_permission(value: object) -> ProviderPermission:
    row = object_fields(value)
    return ProviderPermission(
        identifier(row["provider_id"]),
        text_value(row["policy_version"]),
        timestamp(row["expires_at"]),
        tuple(DataSensitivity(text_value(item)) for item in items(row["sensitivities"])),
        tuple(DataCategory(text_value(item)) for item in items(row["categories"])),
        cast(bool, row["enabled"]),
    )


class ModelPermissionStore:
    def __init__(self, connection: Connection) -> None:
        validate_application_connection(connection)
        self.connection = connection

    def current(self, provider_id: UUID) -> tuple[int, ProviderPermission] | None:
        require_identifier(provider_id)
        require_transaction(self.connection)
        row = self.connection.execute(
            text(
                "SELECT revision,payload FROM acoa.model_provider_permissions WHERE provider_id=:id"
            ),
            {"id": provider_id},
        ).one_or_none()
        if row is None:
            return None
        try:
            permission = decode_permission(row.payload)
            if permission.provider_id != provider_id:
                raise ValueError("Provider permission identity mismatch.")
            return cast(int, row.revision), permission
        except (KeyError, TypeError, ValueError):
            raise DatabaseBoundaryError(
                "Persisted provider scope is invalid; model calls are blocked."
            ) from None

    def publish(
        self, expected_revision: int, permission: ProviderPermission, change_evidence_id: UUID
    ) -> int:
        require_identifier(change_evidence_id)
        if (
            isinstance(expected_revision, bool)
            or not isinstance(expected_revision, int)
            or expected_revision < 0
        ):
            raise DatabaseBoundaryError("Provider revision must be a nonnegative integer.")
        if not isinstance(permission, ProviderPermission):
            raise DatabaseBoundaryError("A validated provider permission is required.")
        AuthorityStore(self.connection).lock_current()
        prior = self.current(permission.provider_id)
        revision = prior[0] if prior else 0
        if revision != expected_revision:
            raise DatabaseBoundaryError("Provider scope changed; reload the current revision.")
        now = cast(datetime, self.connection.execute(text("SELECT clock_timestamp()")).scalar_one())
        if permission.enabled and permission.expires_at <= now:
            raise DatabaseBoundaryError("An enabled provider scope must have a future expiry.")
        seen: bool = self.connection.execute(
            text("""SELECT EXISTS (
            SELECT 1 FROM acoa.model_provider_permission_versions WHERE provider_id=:id
                AND payload->>'policy_version'=:version)"""),
            {"id": permission.provider_id, "version": permission.policy_version},
        ).scalar_one()
        if (
            permission.enabled
            and seen
            and (prior is None or prior[1].policy_version != permission.policy_version)
        ):
            raise DatabaseBoundaryError("An older provider policy version cannot be reinstated.")
        if prior and prior[1].policy_version == permission.policy_version and permission.enabled:
            if prior[1] != permission:
                raise DatabaseBoundaryError(
                    "Provider authority changes require a new policy version."
                )
        encoded = encode_record(asdict(permission))
        values = {
            "id": permission.provider_id,
            "revision": revision + 1,
            "payload": encoded,
            "evidence": change_evidence_id,
        }
        self.connection.execute(
            text("""INSERT INTO acoa.model_provider_permission_versions
            (provider_id,revision,payload,change_evidence_id)
            VALUES (:id,:revision,CAST(:payload AS jsonb),:evidence)"""),
            values,
        )
        self.connection.execute(
            text("""INSERT INTO acoa.model_provider_permissions
            (provider_id,revision,payload,change_evidence_id)
            VALUES (:id,:revision,CAST(:payload AS jsonb),:evidence)
            ON CONFLICT (provider_id) DO UPDATE SET revision=EXCLUDED.revision,
                payload=EXCLUDED.payload,change_evidence_id=EXCLUDED.change_evidence_id"""),
            values,
        )
        return revision + 1
