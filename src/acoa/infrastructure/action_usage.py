"""Authoritative reservation/consumption snapshots; caller holds the global authority lock."""

from datetime import datetime
from decimal import Decimal
from typing import cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from acoa.application.policy_inputs import BudgetUsage, QuotaUsage
from acoa.domain.action_requests import PolicyRequest
from acoa.infrastructure.policy_authority import PolicyAuthority


def quota_usage(
    connection: Connection,
    authority: PolicyAuthority,
    owner_id: UUID,
    company_id: UUID,
    request: PolicyRequest,
    attempt_id: UUID,
    now: datetime,
) -> QuotaUsage:
    """Carry live reservations/unknown attempts across periods; exclude this attempt's own hold."""
    if authority.grant is None or authority.timezone is None:
        return QuotaUsage()
    row = connection.execute(
        text("""
        WITH held AS (
            SELECT x.*, s.company_id,
                x.prepared->'request'->>'recipient_id' AS recipient,
                (x.state IN ('reserved','executing','reconciling','unconfirmed')) AS unsettled
            FROM acoa.external_action_attempts x
            JOIN acoa.applications a ON a.application_id = x.application_id
            JOIN acoa.application_series s ON s.series_id = a.series_id
            WHERE s.owner_id = :owner AND x.attempt_id <> :attempt
              AND x.state NOT IN ('prepared', 'cancelled')
        ) SELECT
            count(*) FILTER (WHERE unsettled OR
                (execution_started_at AT TIME ZONE :zone)::date =
                (CAST(:now AS timestamptz) AT TIME ZONE :zone)::date) AS today,
            count(*) FILTER (WHERE unsettled OR
                date_trunc('week', execution_started_at AT TIME ZONE :zone) =
                date_trunc('week', CAST(:now AS timestamptz) AT TIME ZONE :zone)) AS week,
            count(*) FILTER (WHERE company_id = :company) AS company,
            count(*) FILTER (WHERE recipient = :recipient) AS contact
        FROM held
    """),
        {
            "owner": owner_id,
            "company": company_id,
            "recipient": str(request.recipient_id),
            "attempt": attempt_id,
            "zone": authority.timezone,
            "now": now,
        },
    ).one()
    return QuotaUsage(
        authority.grant.limit_policy_id, row.today, row.week, row.company, row.contact
    )


def budget_usage(
    connection: Connection,
    authority: PolicyAuthority,
    attempt_id: UUID,
    evidence: dict[str, object],
    now: datetime,
) -> BudgetUsage:
    """Pending money remains held even across midnight until verified reconciliation."""
    if authority.timezone is None:
        return BudgetUsage()
    row = connection.execute(
        text("""
        SELECT COALESCE(sum(reserved + CASE
            WHEN (settled_at AT TIME ZONE :zone)::date =
                 (CAST(:now AS timestamptz) AT TIME ZONE :zone)::date THEN consumed ELSE 0 END),0)
                 AS today,
            COALESCE(sum(reserved + CASE
            WHEN date_trunc('month', settled_at AT TIME ZONE :zone) =
                 date_trunc('month', CAST(:now AS timestamptz) AT TIME ZONE :zone)
                 THEN consumed ELSE 0 END),0) AS month
        FROM acoa.budget_ledger WHERE attempt_id <> :attempt AND currency = :currency
    """),
        {
            "attempt": attempt_id,
            "zone": authority.timezone,
            "now": now,
            "currency": authority.settings.budget.currency,
        },
    ).one()
    return BudgetUsage(
        cast(str | None, evidence["currency"]),
        cast(Decimal, row.today),
        cast(Decimal, row.month),
        cast(Decimal | None, evidence["quoted_cost"]),
        cast(int | None, evidence["estimated_tokens"]),
        cast(int | None, evidence["estimated_seconds"]),
    )
