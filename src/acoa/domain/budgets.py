"""Conservative Decimal resource-limit decisions; arithmetic must never hide an overrun."""

from decimal import (
    ROUND_CEILING,
    Decimal,
    DecimalException,
    Inexact,
    InvalidOperation,
    Overflow,
    localcontext,
)
from enum import StrEnum

from acoa.domain.values import DomainError


class LimitCheck(StrEnum):
    WITHIN = "within"
    EXCEEDED = "exceeded"
    INDETERMINATE = "indeterminate"


def check_decimal_limit(used: Decimal, additional: Decimal, limit: Decimal) -> LimitCheck:
    """Use upward rounding only to prove headroom; ambiguous near-cap arithmetic fails closed."""
    if any(
        not isinstance(value, Decimal) or not value.is_finite() or value < 0
        for value in (used, additional, limit)
    ):
        raise DomainError("Resource quantities must be finite nonnegative Decimals.")
    if used > limit or additional > limit:
        return LimitCheck.EXCEEDED
    with localcontext() as context:
        context.rounding = ROUND_CEILING
        context.traps[Inexact] = False
        context.traps[InvalidOperation] = True
        context.traps[Overflow] = True
        context.clear_flags()
        try:
            upper_bound = used + additional
        except DecimalException:
            return LimitCheck.INDETERMINATE
        if upper_bound <= limit:
            return LimitCheck.WITHIN
        return LimitCheck.INDETERMINATE if context.flags[Inexact] else LimitCheck.EXCEEDED
