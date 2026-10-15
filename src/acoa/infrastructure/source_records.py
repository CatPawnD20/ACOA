"""Immutable PostgreSQL records for authorized discovery and source observations."""

import json
from collections.abc import Sequence
from dataclasses import asdict
from hashlib import sha256

from sqlalchemy import text
from sqlalchemy.engine import Connection

from acoa.application.discovery import DiscoveryResult, FetchResult
from acoa.domain.discovery import (
    SourceBatch,
    SourceObservation,
    SourcePolicy,
    SourceSnapshot,
    source_batch_sha256,
    source_snapshot_sha256,
)
from acoa.infrastructure.policy_codec import encode_record
from acoa.infrastructure.postgres import DatabaseBoundaryError, validate_application_connection


def _encoded(
    value: SourcePolicy | SourceBatch | SourceSnapshot | SourceObservation,
) -> tuple[str, str]:
    payload = encode_record(asdict(value))
    return payload, sha256(payload.encode("utf-8")).hexdigest()


def _require_exact(
    prior: Sequence[object] | None,
    digest: str,
    payload: str,
    message: str,
) -> None:
    if prior is None:
        raise DatabaseBoundaryError("An immutable source record disappeared after conflict.")
    prior_digest, prior_payload = prior[0], prior[1]
    if prior_digest != digest or prior_payload != json.loads(payload):
        raise DatabaseBoundaryError(message)


class SourceRecordRepository:
    def __init__(self, connection: Connection) -> None:
        validate_application_connection(connection)
        self.connection = connection

    def record_policy(self, policy: SourcePolicy) -> None:
        if not isinstance(policy, SourcePolicy):
            raise DatabaseBoundaryError("A validated source policy is required.")
        payload, digest = _encoded(policy)
        inserted = self.connection.execute(
            text("""INSERT INTO acoa.source_policies
                (source_id,policy_version,policy_sha256,source_kind,access_allowed,
                 valid_until,policy)
                VALUES (:source,:version,:digest,:kind,:allowed,:valid_until,
                    CAST(:payload AS jsonb))
                ON CONFLICT (source_id,policy_version) DO NOTHING RETURNING source_id"""),
            {
                "source": policy.source_id,
                "version": policy.policy_version,
                "digest": digest,
                "kind": policy.kind.value,
                "allowed": policy.access_allowed,
                "valid_until": policy.valid_until,
                "payload": payload,
            },
        ).scalar_one_or_none()
        if inserted is not None:
            return
        prior = self.connection.execute(
            text("""SELECT policy_sha256,policy FROM acoa.source_policies
                WHERE source_id=:source AND policy_version=:version"""),
            {"source": policy.source_id, "version": policy.policy_version},
        ).one_or_none()
        _require_exact(
            prior,
            digest,
            payload,
            "A source policy version must retain its exact access and license terms.",
        )

    def record_discovery(self, result: DiscoveryResult) -> None:
        if not isinstance(result, DiscoveryResult):
            raise DatabaseBoundaryError("A validated discovery result is required.")
        if result.batch is not None:
            self._record_batch(result.batch)
        self._record_observation(result.observation)

    def record_fetch(self, result: FetchResult) -> None:
        if not isinstance(result, FetchResult):
            raise DatabaseBoundaryError("A validated fetch result is required.")
        if result.document is not None:
            self._record_snapshot(result.document.snapshot)
        self._record_observation(result.observation)

    def _record_batch(self, batch: SourceBatch) -> None:
        payload, _ = _encoded(batch)
        binding = source_batch_sha256(batch)
        inserted = self.connection.execute(
            text("""INSERT INTO acoa.source_batches
                (batch_id,batch_sha256,source_id,source_policy_version,query_sha256,
                 observed_at,batch)
                VALUES (:id,:binding,:source,:policy,:query,:observed_at,
                    CAST(:payload AS jsonb))
                ON CONFLICT (batch_id) DO NOTHING RETURNING batch_id"""),
            {
                "id": batch.batch_id,
                "binding": binding,
                "source": batch.source_id,
                "policy": batch.source_policy_version,
                "query": batch.query_sha256,
                "observed_at": batch.observed_at,
                "payload": payload,
            },
        ).scalar_one_or_none()
        if inserted is not None:
            return
        prior = self.connection.execute(
            text("SELECT batch_sha256,batch FROM acoa.source_batches WHERE batch_id=:id"),
            {"id": batch.batch_id},
        ).one_or_none()
        _require_exact(
            prior,
            binding,
            payload,
            "A source batch ID must retain its exact query and canonical resources.",
        )

    def _record_snapshot(self, snapshot: SourceSnapshot) -> None:
        payload, _ = _encoded(snapshot)
        binding = source_snapshot_sha256(snapshot)
        inserted = self.connection.execute(
            text("""INSERT INTO acoa.source_snapshots
                (snapshot_id,snapshot_sha256,source_id,source_policy_version,
                 resource_sha256,content_sha256,observed_at,valid_until,snapshot)
                VALUES (:id,:binding,:source,:policy,:resource,:content,:observed_at,
                    :valid_until,CAST(:payload AS jsonb))
                ON CONFLICT (snapshot_id) DO NOTHING RETURNING snapshot_id"""),
            {
                "id": snapshot.snapshot_id,
                "binding": binding,
                "source": snapshot.resource.source_id,
                "policy": snapshot.source_policy_version,
                "resource": snapshot.resource.canonical_sha256,
                "content": snapshot.content_sha256,
                "observed_at": snapshot.observed_at,
                "valid_until": snapshot.valid_until,
                "payload": payload,
            },
        ).scalar_one_or_none()
        if inserted is not None:
            return
        prior = self.connection.execute(
            text(
                "SELECT snapshot_sha256,snapshot FROM acoa.source_snapshots WHERE snapshot_id=:id"
            ),
            {"id": snapshot.snapshot_id},
        ).one_or_none()
        _require_exact(
            prior,
            binding,
            payload,
            "A source snapshot ID must retain its exact provenance and content digest.",
        )

    def _record_observation(self, observation: SourceObservation) -> None:
        payload, digest = _encoded(observation)
        inserted = self.connection.execute(
            text("""INSERT INTO acoa.source_access_observations
                (observation_id,observation_sha256,source_id,source_policy_version,
                 operation,status,target_sha256,result_sha256,observed_at,observation)
                VALUES (:id,:digest,:source,:policy,:operation,:status,:target,:result,
                    :observed_at,CAST(:payload AS jsonb))
                ON CONFLICT (observation_id) DO NOTHING RETURNING observation_id"""),
            {
                "id": observation.observation_id,
                "digest": digest,
                "source": observation.source_id,
                "policy": observation.source_policy_version,
                "operation": observation.operation.value,
                "status": observation.status.value,
                "target": observation.target_sha256,
                "result": observation.result_sha256,
                "observed_at": observation.observed_at,
                "payload": payload,
            },
        ).scalar_one_or_none()
        if inserted is not None:
            return
        prior = self.connection.execute(
            text("""SELECT observation_sha256,observation
                FROM acoa.source_access_observations WHERE observation_id=:id"""),
            {"id": observation.observation_id},
        ).one_or_none()
        _require_exact(
            prior,
            digest,
            payload,
            "A source observation ID must retain its exact status and result binding.",
        )
