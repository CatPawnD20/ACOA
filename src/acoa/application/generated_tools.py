"""Validate sandbox output into narrow planning proposals; EP-09.04."""

import json
from hashlib import sha256
from uuid import NAMESPACE_URL, uuid5

from acoa.domain.generated_tools import (
    GeneratedProposalKind,
    GeneratedToolExecution,
    GeneratedToolProposal,
    GeneratedToolRequest,
    GeneratedToolState,
)
from acoa.domain.values import DomainError

OUTPUT_SCHEMA = "acoa-generated-tool-proposals/1"


def mediate_generated_tool_output(
    request: GeneratedToolRequest,
    execution: GeneratedToolExecution,
    output_json: str,
) -> tuple[GeneratedToolProposal, ...]:
    """Return inert planning proposals; this function has no external-action port."""
    if not isinstance(request, GeneratedToolRequest) or not isinstance(
        execution, GeneratedToolExecution
    ):
        raise DomainError("Generated-tool mediation requires validated request and execution.")
    encoded = output_json.encode("utf-8") if isinstance(output_json, str) else b""
    if (
        execution.request_id != request.request_id
        or execution.source_sha256 != request.source_sha256
        or execution.input_sha256 != request.input_sha256
        or execution.state is not GeneratedToolState.SUCCEEDED
        or execution.observed_at < request.created_at
        or execution.observed_at >= request.expires_at
        or len(encoded) > request.maximum_output_bytes
        or sha256(encoded).hexdigest() != execution.output_sha256
    ):
        raise DomainError("Sandbox output does not match the current generated-tool request.")
    payload = _object(output_json)
    if set(payload) != {"schema", "proposals"} or payload["schema"] != OUTPUT_SCHEMA:
        raise DomainError("Generated-tool output uses an unsupported schema.")
    values = payload["proposals"]
    if not isinstance(values, list) or not values or len(values) > 20:
        raise DomainError("Generated-tool output requires a bounded nonempty proposal list.")
    proposals = tuple(
        _proposal(request, execution, index, value) for index, value in enumerate(values)
    )
    if len({(item.kind, item.subject) for item in proposals}) != len(proposals):
        raise DomainError("Generated-tool output cannot repeat a proposal target.")
    return proposals


def _object(value: str) -> dict[str, object]:
    try:
        payload = json.loads(value)
    except (TypeError, ValueError):
        raise DomainError("Generated-tool output must be valid JSON.") from None
    if not isinstance(payload, dict):
        raise DomainError("Generated-tool output must be a JSON object.")
    return payload


def _proposal(
    request: GeneratedToolRequest,
    execution: GeneratedToolExecution,
    index: int,
    value: object,
) -> GeneratedToolProposal:
    if not isinstance(value, dict) or set(value) != {"kind", "subject", "value"}:
        raise DomainError("Generated-tool proposals contain unsupported action fields.")
    kind_value, subject, proposal_value = value["kind"], value["subject"], value["value"]
    if not all(isinstance(item, str) for item in (kind_value, subject, proposal_value)):
        raise DomainError("Generated-tool proposal values must be plain text.")
    try:
        kind = GeneratedProposalKind(kind_value)
    except ValueError:
        raise DomainError("Generated-tool output proposed an unauthorized operation.") from None
    proposal_id = uuid5(NAMESPACE_URL, f"acoa:generated-proposal:{execution.execution_id}:{index}")
    return GeneratedToolProposal(
        proposal_id,
        request.request_id,
        execution.execution_id,
        kind,
        subject,
        proposal_value,
        execution.output_sha256,
        execution.observed_at,
    )
