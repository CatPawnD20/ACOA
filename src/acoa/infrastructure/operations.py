"""Transactional operational audit and systemic safe-mode response; EP-10.03."""

import json
from dataclasses import asdict, replace
from typing import cast

from sqlalchemy import text
from sqlalchemy.engine import Connection

from acoa.domain.operations import (
    ErrorBudgetPolicy,
    HealthObservation,
    OperationalAssessment,
    OperationalResponse,
    assess_dependency_health,
)
from acoa.infrastructure.policy_authority import AuthorityStore, PolicyAuthority
from acoa.infrastructure.policy_codec import encode_record
from acoa.infrastructure.postgres import DatabaseBoundaryError, validate_application_connection


def _safe_mode(authority: PolicyAuthority) -> PolicyAuthority:
    settings = replace(authority.settings, dry_run=True, external_actions_enabled=False)
    return replace(authority, settings=settings, paused=True)


class OperationalRepository:
    """Persist health decisions and enter safe mode atomically for systemic risk."""

    def __init__(self, connection: Connection) -> None:
        validate_application_connection(connection)
        self.connection = connection

    def record(
        self,
        assessment: OperationalAssessment,
        observations: tuple[HealthObservation, ...],
    ) -> None:
        self._validate(assessment, observations)
        for observation in observations:
            self._record_observation(observation)
        if not self._record_assessment(assessment):
            return
        if assessment.response is OperationalResponse.ENTER_SAFE_MODE:
            self._enter_safe_mode(assessment)
        if assessment.response is not OperationalResponse.CONTINUE:
            self._record_alert(assessment)

    @staticmethod
    def _validate(
        assessment: OperationalAssessment,
        observations: tuple[HealthObservation, ...],
    ) -> None:
        if (
            not isinstance(assessment, OperationalAssessment)
            or not observations
            or any(not isinstance(item, HealthObservation) for item in observations)
        ):
            raise DatabaseBoundaryError("Validated operational evidence is required.")
        expected = assess_dependency_health(
            assessment.assessment_id,
            observations,
            ErrorBudgetPolicy(
                maximum_failures=assessment.maximum_failures,
                window_seconds=assessment.window_seconds,
            ),
            assessment.assessed_at,
        )
        if expected != assessment:
            raise DatabaseBoundaryError("Operational assessment evidence does not match.")

    def _record_observation(self, observation: HealthObservation) -> None:
        encoded = encode_record(asdict(observation))
        inserted = self.connection.execute(
            text("""INSERT INTO acoa.operational_health_events
                (observation_id,dependency,state,evidence_sha256,payload,observed_at)
                VALUES (:id,:dependency,:state,:evidence,CAST(:payload AS jsonb),:observed)
                ON CONFLICT (observation_id) DO NOTHING RETURNING observation_id"""),
            {
                "id": observation.observation_id,
                "dependency": observation.dependency.value,
                "state": observation.state.value,
                "evidence": observation.evidence_sha256,
                "payload": encoded,
                "observed": observation.observed_at,
            },
        ).scalar_one_or_none()
        if inserted is None:
            prior: object = self.connection.execute(
                text("SELECT payload FROM acoa.operational_health_events WHERE observation_id=:id"),
                {"id": observation.observation_id},
            ).scalar_one()
            if prior != json.loads(encoded):
                raise DatabaseBoundaryError("A health observation ID must retain exact content.")

    def _record_assessment(self, assessment: OperationalAssessment) -> bool:
        encoded = encode_record(asdict(assessment))
        inserted = self.connection.execute(
            text("""INSERT INTO acoa.operational_assessments
                (assessment_id,dependency,response,failure_count,maximum_failures,
                 window_seconds,payload,assessed_at)
                VALUES (:id,:dependency,:response,:failures,:maximum,:window,
                        CAST(:payload AS jsonb),:assessed)
                ON CONFLICT (assessment_id) DO NOTHING RETURNING assessment_id"""),
            {
                "id": assessment.assessment_id,
                "dependency": assessment.dependency.value,
                "response": assessment.response.value,
                "failures": assessment.failure_count,
                "maximum": assessment.maximum_failures,
                "window": assessment.window_seconds,
                "payload": encoded,
                "assessed": assessment.assessed_at,
            },
        ).scalar_one_or_none()
        if inserted is not None:
            return True
        prior: object = self.connection.execute(
            text("SELECT payload FROM acoa.operational_assessments WHERE assessment_id=:id"),
            {"id": assessment.assessment_id},
        ).scalar_one()
        if prior != json.loads(encoded):
            raise DatabaseBoundaryError("An operational assessment ID must retain exact content.")
        return False

    def _enter_safe_mode(self, assessment: OperationalAssessment) -> None:
        store = AuthorityStore(self.connection)
        revision, authority = store.lock_current()
        safe = _safe_mode(authority)
        if safe != authority:
            store.replace(revision, safe, assessment.assessment_id)

    def _record_alert(self, assessment: OperationalAssessment) -> None:
        systemic = assessment.response is OperationalResponse.ENTER_SAFE_MODE
        critical = systemic or assessment.response is OperationalResponse.ISOLATE_DEPENDENCY
        self.connection.execute(
            text("""INSERT INTO acoa.operational_alerts
                (assessment_id,scope,severity,created_at)
                VALUES (:id,:scope,:severity,:created)"""),
            {
                "id": assessment.assessment_id,
                "scope": "system" if systemic else "dependency",
                "severity": "critical" if critical else "warning",
                "created": assessment.assessed_at,
            },
        )

    def pending_alert_count(self) -> int:
        return cast(
            int,
            self.connection.execute(
                text("SELECT count(*) FROM acoa.operational_alerts WHERE state='pending'")
            ).scalar_one(),
        )
