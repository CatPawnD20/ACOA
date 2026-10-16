"""Append-only PostgreSQL persistence for comparisons and reversible selections."""

import json
from dataclasses import asdict
from hashlib import sha256

from sqlalchemy import text
from sqlalchemy.engine import Connection

from acoa.domain.experiment_comparison import StrategyComparison, StrategySelection
from acoa.infrastructure.policy_codec import encode_record
from acoa.infrastructure.postgres import DatabaseBoundaryError, validate_application_connection


class ExperimentComparisonRepository:
    def __init__(self, connection: Connection) -> None:
        validate_application_connection(connection)
        self.connection = connection

    def record_comparison(self, comparison: StrategyComparison) -> None:
        if not isinstance(comparison, StrategyComparison):
            raise DatabaseBoundaryError("A validated strategy comparison is required.")
        encoded, digest = _encoded_digest(comparison)
        inserted = self.connection.execute(
            text("""INSERT INTO acoa.experiment_comparisons
            (comparison_id,experiment_id,comparison_sha256,gate_version,dataset_sha256,
             sample_count,payload,compared_at)
            VALUES (:id,:experiment,:digest,:gate,:dataset,:samples,CAST(:payload AS jsonb),:at)
            ON CONFLICT (comparison_id) DO NOTHING RETURNING comparison_id"""),
            {
                "id": comparison.comparison_id,
                "experiment": comparison.experiment_id,
                "digest": digest,
                "gate": comparison.gate_version,
                "dataset": comparison.baseline.dataset_sha256,
                "samples": comparison.baseline.sample_count,
                "payload": encoded,
                "at": comparison.compared_at,
            },
        ).scalar_one_or_none()
        if inserted is None:
            _require_same(
                self.connection,
                "SELECT comparison_sha256,payload FROM acoa.experiment_comparisons "
                "WHERE comparison_id=:id",
                comparison.comparison_id,
                digest,
                encoded,
            )

    def record_selection(self, selection: StrategySelection) -> None:
        if not isinstance(selection, StrategySelection):
            raise DatabaseBoundaryError("A validated strategy selection is required.")
        encoded, digest = _encoded_digest(selection)
        inserted = self.connection.execute(
            text("""INSERT INTO acoa.strategy_selections
            (selection_id,comparison_id,experiment_id,selection_sha256,kind,
             selected_strategy_version,restore_strategy_version,payload,selected_at)
            VALUES (:id,:comparison,:experiment,:digest,:kind,:selected,:restore,
                    CAST(:payload AS jsonb),:at)
            ON CONFLICT (selection_id) DO NOTHING RETURNING selection_id"""),
            {
                "id": selection.selection_id,
                "comparison": selection.comparison_id,
                "experiment": selection.experiment_id,
                "digest": digest,
                "kind": selection.kind.value,
                "selected": selection.selected_strategy_version,
                "restore": selection.restore_strategy_version,
                "payload": encoded,
                "at": selection.selected_at,
            },
        ).scalar_one_or_none()
        if inserted is None:
            _require_same(
                self.connection,
                "SELECT selection_sha256,payload FROM acoa.strategy_selections "
                "WHERE selection_id=:id",
                selection.selection_id,
                digest,
                encoded,
            )


def _encoded_digest(value: StrategyComparison | StrategySelection) -> tuple[str, str]:
    encoded = encode_record(asdict(value))
    return encoded, sha256(encoded.encode("utf-8")).hexdigest()


def _require_same(
    connection: Connection,
    statement: str,
    identity: object,
    digest: str,
    encoded: str,
) -> None:
    prior = connection.execute(text(statement), {"id": identity}).one()
    if prior[0] != digest or prior[1] != json.loads(encoded):
        raise DatabaseBoundaryError("An experiment comparison ID must retain exact content.")
