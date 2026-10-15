"""Versioned HMAC cache identities; this task intentionally stores no cached body."""

import hmac
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from hashlib import sha256

from acoa.domain.model_calls import ModelCallRequest
from acoa.domain.model_context import PackedModelContext, require_current_context
from acoa.domain.model_privacy import DataSensitivity
from acoa.domain.model_quality import require_quality
from acoa.domain.model_routing import Severity
from acoa.domain.values import DomainError, require_sha256, require_text, require_timestamp


@dataclass(frozen=True, slots=True)
class ModelCachePolicy:
    policy_version: str
    topic: str
    risk: Severity
    ttl_seconds: int

    def __post_init__(self) -> None:
        require_text(self.policy_version)
        require_text(self.topic)
        if not isinstance(self.risk, Severity):
            raise DomainError("Cache risk must be explicit.")
        if (
            isinstance(self.ttl_seconds, bool)
            or not isinstance(self.ttl_seconds, int)
            or self.ttl_seconds < 1
        ):
            raise DomainError("Cache TTL must be a positive integer.")


@dataclass(frozen=True, slots=True)
class ModelCacheDescriptor:
    key_sha256: str = field(repr=False)
    policy_version: str
    topic: str
    risk: Severity
    context_sha256: str = field(repr=False)
    valid_until: datetime

    def __post_init__(self) -> None:
        require_sha256(self.key_sha256)
        require_text(self.policy_version)
        require_text(self.topic)
        if not isinstance(self.risk, Severity):
            raise DomainError("Cache descriptor risk must be explicit.")
        require_sha256(self.context_sha256)
        require_timestamp(self.valid_until)


def cache_identity_payload(
    request: ModelCallRequest,
    context: PackedModelContext,
    policy: ModelCachePolicy,
    required_quality: Decimal,
) -> bytes:
    require_quality(required_quality)
    payload = {
        "schema": "acoa-model-cache-key/1",
        "cache_policy": policy.policy_version,
        "topic": policy.topic,
        "risk": policy.risk.name,
        "ttl_seconds": policy.ttl_seconds,
        "provider_id": str(request.provider_id),
        "model_alias": request.model_alias,
        "routing_policy": request.routing_policy_version,
        "prompt_version": request.prompt_version,
        "output_schema": request.output_schema_version,
        "instruction_sha256": sha256(request.prompt.encode("utf-8")).hexdigest(),
        "context_sha256": context.context_sha256,
        "context_component_sha256s": list(context.component_sha256s),
        "required_quality": str(required_quality),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def build_cache_descriptor(
    request: ModelCallRequest,
    context: PackedModelContext,
    policy: ModelCachePolicy,
    required_quality: Decimal,
    namespace_key: bytes,
    now: datetime,
) -> ModelCacheDescriptor:
    """Permit reusable identities only for current public context and a protected key."""
    require_timestamp(now)
    require_current_context(context, now)
    if context.sensitivity is not DataSensitivity.PUBLIC or context.categories:
        raise DomainError("Personal or sensitive model context is not cacheable in this release.")
    if not isinstance(namespace_key, bytes) or len(namespace_key) < 32:
        raise DomainError("Cache identity requires at least 32 bytes of secret key material.")
    if (
        request.context_sha256 != context.context_sha256
        or request.context_component_sha256s != context.component_sha256s
    ):
        raise DomainError("Cache identity context does not match the model request.")
    valid_until = now + timedelta(seconds=policy.ttl_seconds)
    if context.valid_until is not None:
        valid_until = min(valid_until, context.valid_until)
    key = hmac.new(
        namespace_key,
        cache_identity_payload(request, context, policy, required_quality),
        sha256,
    ).hexdigest()
    return ModelCacheDescriptor(
        key, policy.policy_version, policy.topic, policy.risk, context.context_sha256, valid_until
    )


def cache_descriptor_is_current(descriptor: ModelCacheDescriptor, now: datetime) -> bool:
    require_timestamp(now)
    return now < descriptor.valid_until
