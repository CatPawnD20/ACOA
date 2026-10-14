"""EP-02.04 evidence-backed terminal outcomes; no submit or provider invocation occurs here."""

import json
from collections.abc import Sequence
from dataclasses import asdict, replace
from datetime import datetime
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping

from acoa.domain.actions import ActionState
from acoa.domain.submission_evidence import (
    IncidentKind,
    SubmissionClaim,
    SubmissionEvidence,
    evidence_matches_attempt,
)
from acoa.domain.values import require_version
from acoa.infrastructure.action_protocol import ActionProtocol
from acoa.infrastructure.incidents import IncidentStore
from acoa.infrastructure.policy_authority import AuthorityStore
from acoa.infrastructure.policy_codec import encode_record
from acoa.infrastructure.postgres import DatabaseBoundaryError, validate_application_connection


class ReconciliationStore:
    """Only trusted read-only verifiers may supply evidence; there is no public ingest endpoint."""

    def __init__(self, connection: Connection) -> None:
        validate_application_connection(connection)
        self.connection = connection

    def _event(
        self, attempt_id: UUID, previous: ActionState, target: ActionState, evidence_id: UUID | None
    ) -> None:
        self.connection.execute(
            text("""INSERT INTO acoa.reconciliation_events
            (event_id, attempt_id, previous_state, new_state, evidence_id)
            VALUES (:event, :attempt, :previous, :target, :evidence)"""),
            {
                "event": uuid4(),
                "attempt": attempt_id,
                "previous": previous.value,
                "target": target.value,
                "evidence": evidence_id,
            },
        )

    def _mark_unknown(
        self, attempt_id: UUID, state: ActionState, kind: IncidentKind
    ) -> ActionState:
        if state in (ActionState.VERIFIED, ActionState.FAILED):
            return state
        self.connection.execute(
            text("""UPDATE acoa.external_action_attempts
            SET state='unconfirmed', updated_at=clock_timestamp() WHERE attempt_id=:id"""),
            {"id": attempt_id},
        )
        if state is not ActionState.UNCONFIRMED:
            self._event(attempt_id, state, ActionState.UNCONFIRMED, None)
        IncidentStore(self.connection).open(attempt_id, kind)
        return ActionState.UNCONFIRMED

    def _store_evidence(self, evidence: SubmissionEvidence) -> None:
        encoded = encode_record(asdict(evidence))
        prior: object = self.connection.execute(
            text("SELECT payload FROM acoa.submission_evidence WHERE evidence_id=:id"),
            {"id": evidence.evidence_id},
        ).scalar_one_or_none()
        if prior is not None:
            if prior != json.loads(encoded):
                raise DatabaseBoundaryError(
                    "An evidence ID must retain its exact original content."
                )
            return
        self.connection.execute(
            text("""INSERT INTO acoa.submission_evidence
            (evidence_id, attempt_id, payload) VALUES (:id,:attempt,CAST(:payload AS jsonb))"""),
            {"id": evidence.evidence_id, "attempt": evidence.attempt_id, "payload": encoded},
        )

    def _pause(self, evidence_id: UUID) -> None:
        store = AuthorityStore(self.connection)
        revision, authority = store.lock_current()
        if not authority.paused:
            store.replace(revision, replace(authority, paused=True), evidence_id)

    def _budget_row(self, attempt_id: UUID) -> RowMapping:
        return (
            self.connection.execute(
                text("SELECT * FROM acoa.budget_ledger WHERE attempt_id=:id FOR UPDATE"),
                {"id": attempt_id},
            )
            .mappings()
            .one()
        )

    def _record_cost_risk(
        self, attempt_id: UUID, evidence: SubmissionEvidence, row: RowMapping
    ) -> None:
        if evidence.actual_cost is not None and (
            evidence.currency != row["currency"] or evidence.actual_cost > row["estimated"]
        ):
            IncidentStore(self.connection).open(attempt_id, IncidentKind.BUDGET_OVERRUN)
            self._pause(evidence.evidence_id)

    def _settle_budget(self, attempt_id: UUID, evidence: SubmissionEvidence) -> None:
        """Unknown actual cost retains its conservative hold; known cost is recorded honestly."""
        if evidence.actual_cost is None:
            return
        row = self._budget_row(attempt_id)
        self._record_cost_risk(attempt_id, evidence, row)
        if evidence.currency != row["currency"]:
            return
        if row["settled_at"] is not None:
            if row["consumed"] != evidence.actual_cost:
                IncidentStore(self.connection).open(attempt_id, IncidentKind.CONFLICTING_EVIDENCE)
                self._pause(evidence.evidence_id)
            return
        self.connection.execute(
            text("""UPDATE acoa.budget_ledger SET reserved=0, consumed=:cost,
            released=GREATEST(estimated-:cost,0), settled_at=clock_timestamp()
            WHERE attempt_id=:id"""),
            {"id": attempt_id, "cost": evidence.actual_cost},
        )

    def record(self, attempt_id: UUID, evidence: SubmissionEvidence | None) -> ActionState:
        _, _, prepared, row, _ = ActionProtocol(self.connection).lock_attempt(attempt_id)
        state = ActionState(row["state"])
        if state not in (
            ActionState.RECONCILING,
            ActionState.UNCONFIRMED,
            ActionState.VERIFIED,
            ActionState.FAILED,
        ):
            raise DatabaseBoundaryError(
                "Only dispatched uncertain/terminal attempts can reconcile."
            )
        if evidence is None:
            return self._mark_unknown(attempt_id, state, IncidentKind.UNKNOWN_SUBMISSION)
        now = cast(datetime, self.connection.execute(text("SELECT clock_timestamp()")).scalar_one())
        if not isinstance(evidence, SubmissionEvidence) or not evidence_matches_attempt(
            evidence, prepared, cast(datetime, row["execution_started_at"]), now
        ):
            IncidentStore(self.connection).open(attempt_id, IncidentKind.INVALID_EVIDENCE)
            return self._mark_unknown(attempt_id, state, IncidentKind.UNKNOWN_SUBMISSION)
        self._store_evidence(evidence)
        if evidence.claim is SubmissionClaim.UNKNOWN:
            if evidence.actual_cost is not None:
                self._record_cost_risk(attempt_id, evidence, self._budget_row(attempt_id))
            return self._mark_unknown(attempt_id, state, IncidentKind.UNKNOWN_SUBMISSION)
        target = (
            ActionState.FAILED
            if evidence.claim is SubmissionClaim.NOT_PERFORMED
            else ActionState.VERIFIED
        )
        if state in (ActionState.VERIFIED, ActionState.FAILED) and state is not target:
            IncidentStore(self.connection).open(attempt_id, IncidentKind.CONFLICTING_EVIDENCE)
            self._pause(evidence.evidence_id)
            return state
        self._record_terminal(attempt_id, prepared.application_id, state, target, evidence)
        return target

    def _record_terminal(
        self,
        attempt_id: UUID,
        application_id: UUID,
        state: ActionState,
        target: ActionState,
        evidence: SubmissionEvidence,
    ) -> None:
        if state is not target:
            self.connection.execute(
                text("""UPDATE acoa.external_action_attempts
                SET state=:state,updated_at=clock_timestamp() WHERE attempt_id=:id"""),
                {"id": attempt_id, "state": target.value},
            )
            self.connection.execute(
                text("""UPDATE acoa.applications SET submission_state=:state
                WHERE application_id=:id"""),
                {
                    "id": application_id,
                    "state": (
                        "submission_verified"
                        if target is ActionState.VERIFIED
                        else "submission_failed"
                    ),
                },
            )
            self._event(attempt_id, state, target, evidence.evidence_id)
        self._settle_budget(attempt_id, evidence)
        IncidentStore(self.connection).resolve_unknown(attempt_id, evidence.evidence_id)

    def recover_abandoned(self, limit: int) -> tuple[UUID, ...]:
        """Expire only committed dispatch deadlines; recovery never invokes a provider."""
        require_version(limit)
        AuthorityStore(self.connection).lock_current()
        ids: Sequence[UUID] = (
            self.connection.execute(
                text("""SELECT x.attempt_id
            FROM acoa.external_action_attempts x JOIN acoa.policy_decisions d USING(attempt_id)
            WHERE x.state='executing' AND d.stage='execute' AND d.result->>'decision'='ALLOW'
              AND (d.result->'dispatch_limits'->>'deadline')::timestamptz <= clock_timestamp()
            ORDER BY x.execution_started_at LIMIT :limit"""),
                {"limit": limit},
            )
            .scalars()
            .all()
        )
        recovered = []
        for attempt_id in ids:
            _, _, _, row, _ = ActionProtocol(self.connection).lock_attempt(attempt_id)
            self._mark_unknown(
                attempt_id, ActionState(row["state"]), IncidentKind.ABANDONED_DISPATCH
            )
            recovered.append(attempt_id)
        return tuple(recovered)
