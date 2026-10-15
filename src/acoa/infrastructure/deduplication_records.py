"""Immutable PostgreSQL records for cross-source identity and fallback decisions."""

import json
from collections.abc import Sequence
from dataclasses import asdict
from hashlib import sha256

from sqlalchemy import text
from sqlalchemy.engine import Connection

from acoa.domain.deduplication import DeduplicationDecision, SourceFallbackPlan
from acoa.infrastructure.policy_codec import encode_record
from acoa.infrastructure.postgres import DatabaseBoundaryError, validate_application_connection


def _encoded(value: DeduplicationDecision | SourceFallbackPlan) -> tuple[str, str]:
    payload = encode_record(asdict(value))
    return payload, sha256(payload.encode("utf-8")).hexdigest()


def _require_exact(prior: Sequence[object] | None, digest: str, payload: str, message: str) -> None:
    if prior is None:
        raise DatabaseBoundaryError("An immutable discovery decision disappeared after conflict.")
    if prior[0] != digest or prior[1] != json.loads(payload):
        raise DatabaseBoundaryError(message)


class DeduplicationRecordRepository:
    def __init__(self, connection: Connection) -> None:
        validate_application_connection(connection)
        self.connection = connection

    def record_decision(self, decision: DeduplicationDecision) -> None:
        if not isinstance(decision, DeduplicationDecision):
            raise DatabaseBoundaryError("A validated deduplication decision is required.")
        payload, digest = _encoded(decision)
        inserted = self.connection.execute(
            text("""INSERT INTO acoa.entity_deduplication_decisions
                (decision_id,version,entity_kind,left_entity_id,right_entity_id,outcome,basis,
                 canonical_entity_id,content_sha256,decided_at,valid_until,decision,record_sha256)
                VALUES (:id,:version,:kind,:left,:right,:outcome,:basis,:canonical,:content,
                    :decided,:valid_until,CAST(:payload AS jsonb),:digest)
                ON CONFLICT (decision_id,version) DO NOTHING RETURNING decision_id"""),
            {
                "id": decision.decision_id,
                "version": decision.version,
                "kind": decision.entity_kind.value,
                "left": decision.left_entity_id,
                "right": decision.right_entity_id,
                "outcome": decision.outcome.value,
                "basis": decision.basis.value,
                "canonical": decision.canonical_entity_id,
                "content": decision.content_sha256,
                "decided": decision.decided_at,
                "valid_until": decision.valid_until,
                "payload": payload,
                "digest": digest,
            },
        ).scalar_one_or_none()
        if inserted is not None:
            return
        prior = self.connection.execute(
            text("""SELECT record_sha256,decision FROM acoa.entity_deduplication_decisions
                WHERE decision_id=:id AND version=:version"""),
            {"id": decision.decision_id, "version": decision.version},
        ).one_or_none()
        _require_exact(prior, digest, payload, "A deduplication version must remain immutable.")

    def record_fallback(self, plan: SourceFallbackPlan) -> None:
        if not isinstance(plan, SourceFallbackPlan):
            raise DatabaseBoundaryError("A validated source fallback plan is required.")
        payload, digest = _encoded(plan)
        inserted = self.connection.execute(
            text("""INSERT INTO acoa.source_fallback_plans
                (plan_id,failed_observation_id,failed_source_id,status,selected_source_id,
                 selected_policy_version,selected_permit_id,content_sha256,planned_at,
                 valid_until,plan,record_sha256)
                VALUES (:id,:observation,:failed_source,:status,:selected_source,
                    :selected_policy,:selected_permit,:content,:planned,:valid_until,
                    CAST(:payload AS jsonb),:digest)
                ON CONFLICT (plan_id) DO NOTHING RETURNING plan_id"""),
            {
                "id": plan.plan_id,
                "observation": plan.failed_observation_id,
                "failed_source": plan.failed_source_id,
                "status": plan.status.value,
                "selected_source": plan.selected_source_id,
                "selected_policy": plan.selected_policy_version,
                "selected_permit": plan.selected_permit_id,
                "content": plan.content_sha256,
                "planned": plan.planned_at,
                "valid_until": plan.valid_until,
                "payload": payload,
                "digest": digest,
            },
        ).scalar_one_or_none()
        if inserted is not None:
            return
        prior = self.connection.execute(
            text("SELECT record_sha256,plan FROM acoa.source_fallback_plans WHERE plan_id=:id"),
            {"id": plan.plan_id},
        ).one_or_none()
        _require_exact(prior, digest, payload, "A source fallback plan must remain immutable.")
