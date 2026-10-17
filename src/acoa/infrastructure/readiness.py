"""Immutable, current-authority activation-readiness evidence; EP-10.04."""

import json
from dataclasses import asdict

from sqlalchemy import text
from sqlalchemy.engine import Connection

from acoa.domain.goals import UserGoals
from acoa.domain.profile import ProfileVariant
from acoa.domain.readiness import (
    ActivationReadinessAssessment,
    ChannelConfiguration,
    assess_activation_readiness,
)
from acoa.infrastructure.policy_authority import AuthorityStore
from acoa.infrastructure.policy_codec import encode_record
from acoa.infrastructure.postgres import DatabaseBoundaryError, validate_application_connection


class ReadinessRepository:
    """Persist a recomputed pre-activation result bound to locked Policy Authority."""

    def __init__(self, connection: Connection) -> None:
        validate_application_connection(connection)
        self.connection = connection

    def record(
        self,
        assessment: ActivationReadinessAssessment,
        profile: ProfileVariant | None,
        goals: UserGoals | None,
        channel_configurations: tuple[ChannelConfiguration, ...],
    ) -> None:
        if not isinstance(assessment, ActivationReadinessAssessment):
            raise DatabaseBoundaryError("A validated readiness assessment is required.")
        revision, authority = AuthorityStore(self.connection).lock_current()
        expected = assess_activation_readiness(
            assessment.assessment_id,
            revision,
            authority.settings,
            authority.grant,
            authority.paused,
            profile,
            goals,
            channel_configurations,
            assessment.assessed_at,
        )
        if expected != assessment:
            raise DatabaseBoundaryError("Readiness evidence does not match current authority.")
        encoded = encode_record(asdict(assessment))
        inserted = self.connection.execute(
            text("""INSERT INTO acoa.activation_readiness_assessments
                (assessment_id,authority_revision,state,profile_variant_id,
                 profile_variant_version,profile_sha256,goals_id,goals_version,
                 goals_sha256,payload,assessed_at)
                VALUES (:id,:revision,:state,:profile_id,:profile_version,:profile_sha,
                        :goals_id,:goals_version,:goals_sha,CAST(:payload AS jsonb),:assessed)
                ON CONFLICT (assessment_id) DO NOTHING RETURNING assessment_id"""),
            {
                "id": assessment.assessment_id,
                "revision": assessment.authority_revision,
                "state": assessment.state.value,
                "profile_id": assessment.profile_variant_id,
                "profile_version": assessment.profile_variant_version,
                "profile_sha": assessment.profile_sha256,
                "goals_id": assessment.goals_id,
                "goals_version": assessment.goals_version,
                "goals_sha": assessment.goals_sha256,
                "payload": encoded,
                "assessed": assessment.assessed_at,
            },
        ).scalar_one_or_none()
        if inserted is not None:
            return
        prior: object = self.connection.execute(
            text(
                "SELECT payload FROM acoa.activation_readiness_assessments WHERE assessment_id=:id"
            ),
            {"id": assessment.assessment_id},
        ).scalar_one()
        if prior != json.loads(encoded):
            raise DatabaseBoundaryError("A readiness assessment ID must retain exact content.")
