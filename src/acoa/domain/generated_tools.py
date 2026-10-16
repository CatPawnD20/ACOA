"""Bound generated-tool requests, execution records and non-authoritative proposals."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from acoa.domain.values import (
    DomainError,
    require_identifier,
    require_sha256,
    require_text,
    require_timestamp,
    require_version,
)


class GeneratedToolState(StrEnum):
    SUCCEEDED = "succeeded"
    REJECTED = "rejected"
    FAILED = "failed"


class GeneratedProposalKind(StrEnum):
    SOURCE_QUERY = "source_query"
    RESEARCH_PRIORITY = "research_priority"
    STRATEGY_NOTE = "strategy_note"


@dataclass(frozen=True, slots=True)
class GeneratedToolRequest:
    request_id: UUID
    task_id: UUID
    experiment_id: UUID
    source_sha256: str = field(repr=False)
    input_sha256: str = field(repr=False)
    timeout_seconds: int
    maximum_output_bytes: int
    created_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        for identifier in (self.request_id, self.task_id, self.experiment_id):
            require_identifier(identifier)
        require_sha256(self.source_sha256)
        require_sha256(self.input_sha256)
        for value in (self.timeout_seconds, self.maximum_output_bytes):
            require_version(value)
        if self.timeout_seconds > 10 or self.maximum_output_bytes > 65_536:
            raise DomainError("Generated-tool resources exceed the sandbox contract.")
        require_timestamp(self.created_at)
        require_timestamp(self.expires_at)
        if self.expires_at <= self.created_at:
            raise DomainError("Generated-tool expiry must follow request creation.")


@dataclass(frozen=True, slots=True)
class GeneratedToolExecution:
    execution_id: UUID
    request_id: UUID
    source_sha256: str = field(repr=False)
    input_sha256: str = field(repr=False)
    output_sha256: str = field(repr=False)
    worker_image_sha256: str = field(repr=False)
    state: GeneratedToolState
    observed_at: datetime

    def __post_init__(self) -> None:
        for identifier in (self.execution_id, self.request_id):
            require_identifier(identifier)
        for digest in (
            self.source_sha256,
            self.input_sha256,
            self.output_sha256,
            self.worker_image_sha256,
        ):
            require_sha256(digest)
        if not isinstance(self.state, GeneratedToolState):
            raise DomainError("Generated-tool execution requires an explicit state.")
        require_timestamp(self.observed_at)


@dataclass(frozen=True, slots=True)
class GeneratedToolProposal:
    proposal_id: UUID
    request_id: UUID
    execution_id: UUID
    kind: GeneratedProposalKind
    subject: str
    value: str = field(repr=False)
    output_sha256: str = field(repr=False)
    proposed_at: datetime

    def __post_init__(self) -> None:
        for identifier in (self.proposal_id, self.request_id, self.execution_id):
            require_identifier(identifier)
        if not isinstance(self.kind, GeneratedProposalKind):
            raise DomainError("Generated-tool proposals require an explicit safe kind.")
        for text in (self.subject, self.value):
            require_text(text)
            if len(text) > 500 or any(ord(character) < 32 for character in text):
                raise DomainError("Generated-tool proposal text must be bounded plain text.")
        require_sha256(self.output_sha256)
        require_timestamp(self.proposed_at)
