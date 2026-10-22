"""Closed JSON codecs for trusted persisted policy records; never deserialize agent plans."""

import json
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
from typing import cast
from uuid import UUID

from acoa.application.decision_records import serialize_snapshot_value
from acoa.application.policy_inputs import (
    CommunicationPurpose,
    EvidenceStatus,
    PolicyContext,
    PolicyEvidence,
    Requirement,
)
from acoa.config import Settings, settings_from_mapping
from acoa.domain.action_requests import PolicyRequest
from acoa.domain.authorization import (
    ActionKind,
    AuthorizationGrant,
    Channel,
    DataCategory,
    RecipientClass,
    SensitiveDataConsent,
)
from acoa.domain.reviews import ReviewDecision, UserReview


def encode_record(record: object) -> str:
    """Serialize a caller-selected dataclass payload without file/network access."""
    return json.dumps(record, default=serialize_snapshot_value, sort_keys=True, allow_nan=False)


def object_fields(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValueError("A policy record must be a JSON object.")
    return cast(dict[str, object], value)


def timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("A persisted timestamp must be explicit.")
    return datetime.fromisoformat(value)


def identifier(value: object) -> UUID:
    if not isinstance(value, str):
        raise ValueError("A persisted identifier must be explicit.")
    return UUID(value)


def items(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValueError("A persisted scope must be a JSON array.")
    return value


def text_value(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("A persisted enum must be an explicit string.")
    return value


def decode_review(value: object) -> UserReview | None:
    if value is None:
        return None
    row = object_fields(value)
    return UserReview(
        identifier(row["review_id"]),
        identifier(row["target_id"]),
        cast(int, row["target_version"]),
        cast(str, row["content_sha256"]),
        ReviewDecision(text_value(row["decision"])),
        timestamp(row["reviewed_at"]),
    )


def decode_grant(value: object) -> AuthorizationGrant | None:
    if value is None:
        return None
    row = object_fields(value)
    return AuthorizationGrant(
        identifier(row["grant_id"]),
        cast(int, row["version"]),
        cast(str, row["policy_version"]),
        timestamp(row["starts_at"]),
        timestamp(row["expires_at"]),
        tuple(ActionKind(text_value(item)) for item in items(row["actions"])),
        tuple(Channel(text_value(item)) for item in items(row["channels"])),
        tuple(identifier(item) for item in items(row["recipient_ids"])),
        tuple(identifier(item) for item in items(row["account_ids"])),
        tuple(DataCategory(text_value(item)) for item in items(row["data_categories"])),
        identifier(row["limit_policy_id"]),
        timestamp(row["created_at"]),
        decode_review(row["approval"]),
        timestamp(row["revoked_at"]) if row["revoked_at"] is not None else None,
        tuple(RecipientClass(text_value(item)) for item in items(row.get("recipient_classes", []))),
    )


def decode_consent(value: object) -> SensitiveDataConsent:
    row = object_fields(value)
    return SensitiveDataConsent(
        identifier(row["consent_id"]),
        cast(int, row["version"]),
        identifier(row["grant_id"]),
        cast(int, row["grant_version"]),
        cast(str, row["grant_sha256"]),
        tuple(DataCategory(text_value(item)) for item in items(row["categories"])),
        timestamp(row["starts_at"]),
        timestamp(row["expires_at"]),
        timestamp(row["created_at"]),
        decode_review(row["approval"]),
        timestamp(row["revoked_at"]) if row["revoked_at"] is not None else None,
    )


def decode_settings(value: object) -> Settings:
    row = object_fields(value).copy()
    budget = object_fields(row.get("budget", {})).copy()
    for name in ("max_currency_per_day", "max_currency_per_month"):
        if isinstance(budget.get(name), str):
            budget[name] = Decimal(cast(str, budget[name]))
    row["budget"] = budget
    return settings_from_mapping(row)


def decode_request(value: object) -> PolicyRequest:
    row = object_fields(value)
    return PolicyRequest(
        identifier(row["request_id"]),
        ActionKind(text_value(row["action"])),
        cast(str, row["content_sha256"]),
        Channel(text_value(row["channel"])) if row["channel"] is not None else None,
        identifier(row["recipient_id"]) if row["recipient_id"] is not None else None,
        identifier(row["account_id"]) if row["account_id"] is not None else None,
        tuple(DataCategory(text_value(item)) for item in items(row["data_categories"])),
    )


def encode_evidence_context(context: PolicyContext, prepared_sha256: str) -> str:
    """Persist only validated facts; caller-supplied usage and authority are discarded."""
    return encode_record(
        {
            "prepared_sha256": prepared_sha256,
            "snapshot_at": context.snapshot_at,
            "request_binding_sha256": context.request_binding_sha256,
            "artifact_content_sha256": context.artifact_content_sha256,
            "artifact_categories": context.artifact_categories,
            "purpose": context.purpose,
            "account_email": context.account_email,
            "evidence": [asdict(item) for item in context.evidence],
        }
    )


def decode_evidence_context(value: object, now: datetime) -> PolicyContext:
    row = object_fields(value)
    evidence = tuple(object_fields(item) for item in items(row["evidence"]))
    return PolicyContext(
        now=now,
        snapshot_at=timestamp(row["snapshot_at"]),
        request_binding_sha256=cast(str | None, row["request_binding_sha256"]),
        artifact_content_sha256=cast(str | None, row["artifact_content_sha256"]),
        artifact_categories=tuple(
            DataCategory(text_value(item)) for item in items(row["artifact_categories"])
        ),
        purpose=CommunicationPurpose(text_value(row["purpose"])),
        account_email=cast(str | None, row["account_email"]),
        evidence=tuple(
            PolicyEvidence(
                Requirement(text_value(item["requirement"])),
                EvidenceStatus(text_value(item["status"])),
            )
            for item in evidence
        ),
    )
