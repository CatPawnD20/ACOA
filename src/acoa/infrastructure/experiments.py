"""Append-only PostgreSQL records for strategy experiment plans and checkpoints."""

import json
from dataclasses import asdict
from hashlib import sha256

from sqlalchemy import text
from sqlalchemy.engine import Connection

from acoa.domain.experiments import ExperimentCheckpoint, StrategyExperiment
from acoa.infrastructure.policy_codec import encode_record
from acoa.infrastructure.postgres import DatabaseBoundaryError, validate_application_connection


class ExperimentRepository:
    def __init__(self, connection: Connection) -> None:
        validate_application_connection(connection)
        self.connection = connection

    def record_plan(self, experiment: StrategyExperiment) -> None:
        if not isinstance(experiment, StrategyExperiment):
            raise DatabaseBoundaryError("A validated strategy experiment is required.")
        encoded = encode_record(asdict(experiment))
        digest = sha256(encoded.encode("utf-8")).hexdigest()
        inserted = self.connection.execute(
            text("""INSERT INTO acoa.strategy_experiments
            (experiment_id,task_id,plan_sha256,mode,baseline_strategy_version,
             candidate_strategy_version,maximum_cases,maximum_external_impact,maximum_cost,
             currency,expires_at,payload)
            VALUES (:id,:task,:digest,:mode,:baseline,:candidate,:cases,:impact,:cost,
                    :currency,:expires,CAST(:payload AS jsonb))
            ON CONFLICT (experiment_id) DO NOTHING RETURNING experiment_id"""),
            {
                "id": experiment.experiment_id,
                "task": experiment.task_id,
                "digest": digest,
                "mode": experiment.mode.value,
                "baseline": experiment.baseline_strategy_version,
                "candidate": experiment.candidate_strategy_version,
                "cases": experiment.maximum_cases,
                "impact": experiment.maximum_external_impact,
                "cost": experiment.maximum_cost,
                "currency": experiment.currency,
                "expires": experiment.expires_at,
                "payload": encoded,
            },
        ).scalar_one_or_none()
        if inserted is None:
            self._require_same(
                "strategy_experiments", "experiment_id", experiment.experiment_id, digest, encoded
            )

    def record_checkpoint(self, checkpoint: ExperimentCheckpoint) -> None:
        if not isinstance(checkpoint, ExperimentCheckpoint):
            raise DatabaseBoundaryError("A validated experiment checkpoint is required.")
        encoded = encode_record(asdict(checkpoint))
        digest = sha256(encoded.encode("utf-8")).hexdigest()
        inserted = self.connection.execute(
            text("""INSERT INTO acoa.experiment_checkpoints
            (checkpoint_id,experiment_id,sequence,checkpoint_sha256,state,completed_cases,
             external_impact,actual_cost,currency,payload,observed_at)
            VALUES (:id,:experiment,:sequence,:digest,:state,:cases,:impact,:cost,:currency,
                    CAST(:payload AS jsonb),:observed)
            ON CONFLICT (checkpoint_id) DO NOTHING RETURNING checkpoint_id"""),
            {
                "id": checkpoint.checkpoint_id,
                "experiment": checkpoint.experiment_id,
                "sequence": checkpoint.sequence,
                "digest": digest,
                "state": checkpoint.state.value,
                "cases": checkpoint.completed_cases,
                "impact": checkpoint.external_impact,
                "cost": checkpoint.actual_cost,
                "currency": checkpoint.currency,
                "payload": encoded,
                "observed": checkpoint.observed_at,
            },
        ).scalar_one_or_none()
        if inserted is None:
            self._require_same(
                "experiment_checkpoints",
                "checkpoint_id",
                checkpoint.checkpoint_id,
                digest,
                encoded,
            )

    def _require_same(
        self, table: str, identity_column: str, identity: object, digest: str, encoded: str
    ) -> None:
        if table == "strategy_experiments" and identity_column == "experiment_id":
            statement = text(
                "SELECT plan_sha256,payload FROM acoa.strategy_experiments WHERE experiment_id=:id"
            )
        elif table == "experiment_checkpoints" and identity_column == "checkpoint_id":
            statement = text(
                "SELECT checkpoint_sha256,payload FROM acoa.experiment_checkpoints "
                "WHERE checkpoint_id=:id"
            )
        else:
            raise DatabaseBoundaryError("Unsupported experiment record identity.")
        prior = self.connection.execute(
            statement,
            {"id": identity},
        ).one()
        if prior[0] != digest or prior[1] != json.loads(encoded):
            raise DatabaseBoundaryError("An experiment record ID must retain exact content.")
