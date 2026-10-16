"""Append-only PostgreSQL audit records for generated-tool mediation."""

import json
from dataclasses import asdict
from hashlib import sha256

from sqlalchemy import text
from sqlalchemy.engine import Connection

from acoa.domain.generated_tools import (
    GeneratedToolExecution,
    GeneratedToolProposal,
    GeneratedToolRequest,
)
from acoa.infrastructure.policy_codec import encode_record
from acoa.infrastructure.postgres import DatabaseBoundaryError, validate_application_connection


class GeneratedToolRepository:
    def __init__(self, connection: Connection) -> None:
        validate_application_connection(connection)
        self.connection = connection

    def record_request(self, request: GeneratedToolRequest) -> None:
        if not isinstance(request, GeneratedToolRequest):
            raise DatabaseBoundaryError("A validated generated-tool request is required.")
        encoded, digest = _encoded(request)
        inserted = self.connection.execute(
            text("""INSERT INTO acoa.generated_tool_requests
            (request_id,task_id,experiment_id,source_sha256,input_sha256,request_sha256,
             payload,expires_at)
            VALUES (:id,:task,:experiment,:source,:input,:digest,CAST(:payload AS jsonb),:expires)
            ON CONFLICT (request_id) DO NOTHING RETURNING request_id"""),
            {
                "id": request.request_id,
                "task": request.task_id,
                "experiment": request.experiment_id,
                "source": request.source_sha256,
                "input": request.input_sha256,
                "digest": digest,
                "payload": encoded,
                "expires": request.expires_at,
            },
        ).scalar_one_or_none()
        if inserted is None:
            self._same("request", request.request_id, digest, encoded)

    def record_execution(self, execution: GeneratedToolExecution) -> None:
        if not isinstance(execution, GeneratedToolExecution):
            raise DatabaseBoundaryError("A validated generated-tool execution is required.")
        encoded, digest = _encoded(execution)
        inserted = self.connection.execute(
            text("""INSERT INTO acoa.generated_tool_executions
            (execution_id,request_id,execution_sha256,state,output_sha256,worker_image_sha256,
             payload,observed_at)
            VALUES (:id,:request,:digest,:state,:output,:image,CAST(:payload AS jsonb),:observed)
            ON CONFLICT (execution_id) DO NOTHING RETURNING execution_id"""),
            {
                "id": execution.execution_id,
                "request": execution.request_id,
                "digest": digest,
                "state": execution.state.value,
                "output": execution.output_sha256,
                "image": execution.worker_image_sha256,
                "payload": encoded,
                "observed": execution.observed_at,
            },
        ).scalar_one_or_none()
        if inserted is None:
            self._same("execution", execution.execution_id, digest, encoded)

    def record_proposals(self, proposals: tuple[GeneratedToolProposal, ...]) -> None:
        if not proposals or any(not isinstance(item, GeneratedToolProposal) for item in proposals):
            raise DatabaseBoundaryError("Validated generated-tool proposals are required.")
        for proposal in proposals:
            encoded, digest = _encoded(proposal)
            inserted = self.connection.execute(
                text("""INSERT INTO acoa.generated_tool_proposals
                (proposal_id,request_id,execution_id,proposal_sha256,kind,subject,payload,proposed_at)
                VALUES (:id,:request,:execution,:digest,:kind,:subject,
                        CAST(:payload AS jsonb),:proposed)
                ON CONFLICT (proposal_id) DO NOTHING RETURNING proposal_id"""),
                {
                    "id": proposal.proposal_id,
                    "request": proposal.request_id,
                    "execution": proposal.execution_id,
                    "digest": digest,
                    "kind": proposal.kind.value,
                    "subject": proposal.subject,
                    "payload": encoded,
                    "proposed": proposal.proposed_at,
                },
            ).scalar_one_or_none()
            if inserted is None:
                self._same("proposal", proposal.proposal_id, digest, encoded)

    def _same(self, kind: str, identity: object, digest: str, encoded: str) -> None:
        statements = {
            "request": (
                "SELECT request_sha256,payload FROM acoa.generated_tool_requests "
                "WHERE request_id=:id"
            ),
            "execution": (
                "SELECT execution_sha256,payload FROM acoa.generated_tool_executions "
                "WHERE execution_id=:id"
            ),
            "proposal": (
                "SELECT proposal_sha256,payload FROM acoa.generated_tool_proposals "
                "WHERE proposal_id=:id"
            ),
        }
        statement = statements.get(kind)
        if statement is None:
            raise DatabaseBoundaryError("Unsupported generated-tool record kind.")
        prior = self.connection.execute(text(statement), {"id": identity}).one()
        if prior[0] != digest or prior[1] != json.loads(encoded):
            raise DatabaseBoundaryError("A generated-tool record ID must retain exact content.")


def _encoded(
    value: GeneratedToolRequest | GeneratedToolExecution | GeneratedToolProposal,
) -> tuple[str, str]:
    encoded = encode_record(asdict(value))
    return encoded, sha256(encoded.encode("utf-8")).hexdigest()
