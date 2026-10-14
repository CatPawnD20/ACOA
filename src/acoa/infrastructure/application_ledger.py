"""EP-02.02 canonical application ledger; F-10, P-11/P-15, ADR-007/013."""

import json
from dataclasses import asdict
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping

from acoa.domain.applications import (
    ApplicationIdentity,
    ApplicationKind,
    ApplicationSnapshot,
    ApplicationSpec,
    ApplicationState,
    ReapplicationEvidence,
    SubmissionState,
    reapplication_evidence_is_valid,
    semantic_operation_key,
)
from acoa.domain.values import require_identifier
from acoa.infrastructure.postgres import (
    DatabaseBoundaryError,
    require_transaction,
    validate_application_connection,
)

APPLICATION_SELECT = """
    SELECT a.*, s.owner_id, s.company_id, s.target_id, s.kind
    FROM acoa.applications a JOIN acoa.application_series s ON s.series_id = a.series_id
"""


class LedgerError(DatabaseBoundaryError):
    """A structured ledger rejection without recipient, account or content values."""


def application_from_row(row: RowMapping) -> ApplicationSnapshot:
    """Decode canonical identifiers without deriving identity from a transport URL."""
    identity = ApplicationIdentity(
        cast(UUID, row["owner_id"]),
        cast(UUID, row["company_id"]),
        cast(UUID, row["target_id"]),
        cast(UUID, row["campaign_id"]),
        ApplicationKind(row["kind"]),
    )
    spec = ApplicationSpec(
        cast(UUID, row["application_id"]),
        identity,
        cast(UUID, row["identity_evidence_id"]),
        cast(UUID | None, row["reapplication_episode_id"]),
        cast(UUID | None, row["previous_application_id"]),
    )
    return ApplicationSnapshot(
        spec,
        ApplicationState(row["state"]),
        SubmissionState(row["submission_state"]),
        cast(datetime, row["created_at"]),
        cast(datetime | None, row["closed_at"]),
        cast(UUID | None, row["closure_evidence_id"]),
    )


def encode_evidence_value(value: object) -> str:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    raise LedgerError("Reapplication evidence contains an unsupported value type.")


class ApplicationLedger:
    """Records intent/history only; registration never implies submission or authority."""

    def __init__(self, connection: Connection) -> None:
        validate_application_connection(connection)
        self.connection = connection

    def get(self, application_id: UUID) -> ApplicationSnapshot | None:
        require_identifier(application_id)
        require_transaction(self.connection)
        row = (
            self.connection.execute(
                text(APPLICATION_SELECT + " WHERE a.application_id = :id"), {"id": application_id}
            )
            .mappings()
            .one_or_none()
        )
        return application_from_row(row) if row is not None else None

    def _lock_series(self, identity: ApplicationIdentity) -> UUID:
        """Campaign/channel changes cannot create a second initial episode for the same target."""
        require_transaction(self.connection)
        parameters = {
            "owner": identity.owner_id,
            "company": identity.company_id,
            "target": identity.target_id,
            "kind": identity.kind.value,
        }
        self.connection.execute(
            text("""INSERT INTO acoa.application_series
                 (series_id, owner_id, company_id, target_id, kind)
                 VALUES (:id, :owner, :company, :target, :kind)
                 ON CONFLICT (owner_id, company_id, target_id, kind) DO NOTHING"""),
            {**parameters, "id": uuid4()},
        )
        return cast(
            UUID,
            self.connection.execute(
                text("""SELECT series_id FROM acoa.application_series
                 WHERE owner_id = :owner AND company_id = :company
                   AND target_id = :target AND kind = :kind FOR UPDATE"""),
                parameters,
            ).scalar_one(),
        )

    def _latest(self, series_id: UUID) -> ApplicationSnapshot | None:
        row = (
            self.connection.execute(
                text(
                    APPLICATION_SELECT
                    + """ WHERE a.series_id = :series
                 AND NOT EXISTS (SELECT 1 FROM acoa.applications successor
                     WHERE successor.previous_application_id = a.application_id)"""
                ),
                {"series": series_id},
            )
            .mappings()
            .one_or_none()
        )
        return application_from_row(row) if row is not None else None

    def _check_reapplication(
        self,
        spec: ApplicationSpec,
        previous: ApplicationSnapshot | None,
        evidence: ReapplicationEvidence | None,
    ) -> None:
        if (
            previous is None
            or spec.previous_application_id != previous.spec.application_id
            or previous.state not in (ApplicationState.REJECTED, ApplicationState.CLOSED)
            or previous.submission_state is SubmissionState.UNCONFIRMED
            or previous.spec.reapplication_episode_id == spec.reapplication_episode_id
            or evidence is None
        ):
            raise LedgerError("Reapplication requires a resolved rejected/closed latest episode.")
        now = cast(datetime, self.connection.execute(text("SELECT clock_timestamp()")).scalar_one())
        if (
            not reapplication_evidence_is_valid(spec, evidence, now)
            or evidence.evaluated_at is None
            or previous.closed_at is None
            or evidence.evaluated_at < previous.closed_at
        ):
            raise LedgerError(
                "Reapplication policy, cooldown, change or fresh authority is unresolved."
            )

    def _event(
        self,
        application_id: UUID,
        previous: ApplicationState | None,
        state: ApplicationState,
        evidence_id: UUID,
    ) -> None:
        self.connection.execute(
            text("""INSERT INTO acoa.application_events
                 (event_id, application_id, previous_state, new_state, evidence_id)
                 VALUES (:event, :application, :previous, :state, :evidence)"""),
            {
                "event": uuid4(),
                "application": application_id,
                "previous": previous.value if previous else None,
                "state": state.value,
                "evidence": evidence_id,
            },
        )

    def _insert(
        self,
        spec: ApplicationSpec,
        series_id: UUID,
        evidence: ReapplicationEvidence | None,
    ) -> ApplicationSnapshot:
        encoded = json.dumps(asdict(evidence), default=encode_evidence_value) if evidence else None
        self.connection.execute(
            text("""INSERT INTO acoa.applications
                 (application_id, series_id, campaign_id, identity_evidence_id, semantic_key,
                  reapplication_episode_id, previous_application_id, reapplication_evidence)
                 VALUES (:id, :series, :campaign, :identity, :key, :episode, :previous,
                     CAST(:evidence AS jsonb))"""),
            {
                "id": spec.application_id,
                "series": series_id,
                "campaign": spec.identity.campaign_id,
                "identity": spec.identity_evidence_id,
                "key": semantic_operation_key(spec),
                "episode": spec.reapplication_episode_id,
                "previous": spec.previous_application_id,
                "evidence": encoded,
            },
        )
        self._event(
            spec.application_id,
            None,
            ApplicationState.OPEN,
            evidence.evidence_id if evidence else spec.identity_evidence_id,
        )
        result = self.get(spec.application_id)
        if result is None:
            raise LedgerError("The inserted application is missing.")
        return result

    def register(
        self,
        spec: ApplicationSpec,
        evidence: ReapplicationEvidence | None = None,
    ) -> ApplicationSnapshot:
        """Serialize episodes per canonical target; exact repeated registration is idempotent."""
        if not isinstance(spec, ApplicationSpec) or (
            evidence is not None and not isinstance(evidence, ReapplicationEvidence)
        ):
            raise LedgerError(
                "Registration requires explicit validated application/evidence values."
            )
        series_id = self._lock_series(spec.identity)
        existing = self.get(spec.application_id)
        if existing is not None:
            if existing.spec != spec:
                raise LedgerError("An application ID must retain its original specification.")
            return existing
        previous = self._latest(series_id)
        if spec.reapplication_episode_id is None:
            if previous is not None or evidence is not None:
                raise LedgerError("This target already has an initial application episode.")
        else:
            self._check_reapplication(spec, previous, evidence)
        return self._insert(spec, series_id, evidence)

    def close(
        self,
        application_id: UUID,
        state: ApplicationState,
        evidence_id: UUID,
    ) -> ApplicationSnapshot:
        """Attach lifecycle evidence without erasing or fabricating delivery results."""
        require_identifier(evidence_id)
        if not isinstance(state, ApplicationState) or state is ApplicationState.OPEN:
            raise LedgerError("Closure requires an explicit terminal lifecycle state.")
        application = self.get(application_id)
        if application is None:
            raise LedgerError("The application to close is missing.")
        self._lock_series(application.spec.identity)
        row = (
            self.connection.execute(
                text(APPLICATION_SELECT + " WHERE a.application_id = :id FOR UPDATE OF a"),
                {"id": application_id},
            )
            .mappings()
            .one()
        )
        application = application_from_row(row)
        if application.submission_state is SubmissionState.UNCONFIRMED:
            raise LedgerError("Unconfirmed delivery must be reconciled before lifecycle closure.")
        if application.state is not ApplicationState.OPEN:
            if application.state is state and application.closure_evidence_id == evidence_id:
                return application
            raise LedgerError("Terminal application history cannot be silently rewritten.")
        self.connection.execute(
            text("""UPDATE acoa.applications SET state = :state, closed_at = clock_timestamp(),
                 closure_evidence_id = :evidence WHERE application_id = :id"""),
            {"id": application_id, "state": state.value, "evidence": evidence_id},
        )
        self._event(application_id, application.state, state, evidence_id)
        result = self.get(application_id)
        if result is None:
            raise LedgerError("The closed application is missing.")
        return result
