"""Shared domain value validation; E-06/E-07; no I/O or value disclosure."""

import re
from datetime import datetime
from uuid import UUID


class DomainError(ValueError):
    """A domain invariant violation reported without personal values."""


def require_identifier(value: object) -> None:
    """Require a concrete UUID rather than coercing a supplied identifier."""
    if not isinstance(value, UUID):
        raise DomainError("An identifier must be a UUID.")


def require_version(value: object) -> None:
    """Reject missing, boolean and nonpositive version counters."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise DomainError("A version must be a positive integer.")


def require_timestamp(value: object) -> None:
    """Require an aware timestamp so comparisons do not assume a local timezone."""
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise DomainError("A timestamp must include a timezone.")


def require_text(value: object) -> None:
    """Require explicit, nonempty text without normalizing personal content."""
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise DomainError("A text value must be nonempty and have no outer whitespace.")


def require_sha256(value: object) -> None:
    """Require a canonical content digest rather than accepting arbitrary approval text."""
    if not isinstance(value, str) or re.fullmatch(r"[a-f0-9]{64}", value) is None:
        raise DomainError("A content digest must be a lowercase SHA-256 hexadecimal value.")
