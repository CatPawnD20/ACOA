"""Immutable PostgreSQL metadata for portable application artifacts."""

import json
from dataclasses import asdict

from sqlalchemy import text
from sqlalchemy.engine import Connection

from acoa.domain.artifacts import ArtifactVersion
from acoa.infrastructure.policy_codec import encode_record
from acoa.infrastructure.postgres import DatabaseBoundaryError, validate_application_connection


class ArtifactRecordRepository:
    def __init__(self, connection: Connection) -> None:
        validate_application_connection(connection)
        self.connection = connection

    def record(self, artifact: ArtifactVersion) -> None:
        if not isinstance(artifact, ArtifactVersion):
            raise DatabaseBoundaryError("A validated artifact version is required.")
        payload = encode_record(asdict(artifact))
        self.connection.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(CAST(:artifact AS text),0))"),
            {"artifact": artifact.artifact_id},
        )
        prior = self.connection.execute(
            text("""SELECT record_sha256,metadata FROM acoa.application_artifacts
                WHERE artifact_id=:artifact AND version=:version"""),
            {"artifact": artifact.artifact_id, "version": artifact.version},
        ).one_or_none()
        if prior is not None:
            if prior[0] != artifact.record_sha256 or prior[1] != json.loads(payload):
                raise DatabaseBoundaryError("An artifact version must remain immutable.")
            return
        latest = self.connection.execute(
            text("""SELECT version,application_id,kind FROM acoa.application_artifacts
                WHERE artifact_id=:artifact ORDER BY version DESC LIMIT 1"""),
            {"artifact": artifact.artifact_id},
        ).one_or_none()
        if latest is None:
            if artifact.version != 1:
                raise DatabaseBoundaryError("A new artifact must begin at version one.")
        elif (
            artifact.version != latest[0] + 1
            or artifact.application_id != latest[1]
            or artifact.kind.value != latest[2]
        ):
            raise DatabaseBoundaryError(
                "An artifact version must extend one application and material kind in order."
            )
        self.connection.execute(
            text("""INSERT INTO acoa.application_artifacts
                (artifact_id,version,application_id,kind,source_draft_id,
                 source_binding_sha256,media_type,content_sha256,content_size,
                 storage_key,created_at,record_sha256,metadata)
                VALUES (:artifact,:version,:application,:kind,:draft,:source_hash,
                    :media_type,:content_hash,:content_size,:storage_key,:created,
                    :record_hash,CAST(:metadata AS jsonb))"""),
            {
                "artifact": artifact.artifact_id,
                "version": artifact.version,
                "application": artifact.application_id,
                "kind": artifact.kind.value,
                "draft": artifact.source_draft_id,
                "source_hash": artifact.source_binding_sha256,
                "media_type": artifact.media_type,
                "content_hash": artifact.content_sha256,
                "content_size": artifact.content_size,
                "storage_key": artifact.storage_key,
                "created": artifact.created_at,
                "record_hash": artifact.record_sha256,
                "metadata": payload,
            },
        )
