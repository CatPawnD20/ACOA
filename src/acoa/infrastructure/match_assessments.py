"""Immutable PostgreSQL persistence for version-bound match assessments."""

import json
from dataclasses import asdict

from sqlalchemy import text
from sqlalchemy.engine import Connection

from acoa.application.matching import assessment_binding_sha256
from acoa.domain.matching import MatchAssessment
from acoa.infrastructure.policy_codec import encode_record
from acoa.infrastructure.postgres import DatabaseBoundaryError, validate_application_connection


class MatchAssessmentRepository:
    def __init__(self, connection: Connection) -> None:
        validate_application_connection(connection)
        self.connection = connection

    def record(self, assessment: MatchAssessment) -> None:
        if not isinstance(assessment, MatchAssessment):
            raise DatabaseBoundaryError("A validated match assessment is required.")
        binding = assessment_binding_sha256(assessment)
        encoded = encode_record(asdict(assessment))
        values = {
            "id": assessment.assessment_id,
            "binding": binding,
            "variant": assessment.reference.variant_id,
            "variant_version": assessment.reference.variant_version,
            "goals": assessment.reference.goals_id,
            "goals_version": assessment.reference.goals_version,
            "opportunity": assessment.opportunity_id,
            "opportunity_version": assessment.opportunity_version,
            "opportunity_hash": assessment.opportunity_sha256,
            "policy": assessment.policy_version,
            "classification": assessment.classification.value,
            "result": encoded,
            "valid_until": assessment.valid_until,
        }
        inserted = self.connection.execute(
            text("""INSERT INTO acoa.match_assessments
            (assessment_id,assessment_sha256,profile_variant_id,profile_variant_version,
             goals_id,goals_version,opportunity_id,opportunity_version,opportunity_sha256,
             policy_version,classification,result,valid_until)
            VALUES (:id,:binding,:variant,:variant_version,:goals,:goals_version,
                :opportunity,:opportunity_version,:opportunity_hash,:policy,:classification,
                CAST(:result AS jsonb),:valid_until)
            ON CONFLICT (assessment_id) DO NOTHING RETURNING assessment_id"""),
            values,
        ).scalar_one_or_none()
        if inserted is not None:
            return
        prior = self.connection.execute(
            text("""SELECT assessment_sha256,result FROM acoa.match_assessments
                WHERE assessment_id=:id"""),
            {"id": assessment.assessment_id},
        ).one()
        if prior.assessment_sha256 != binding or prior.result != json.loads(encoded):
            raise DatabaseBoundaryError(
                "A match assessment ID must retain its exact inputs and result."
            )
