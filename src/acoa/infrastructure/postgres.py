"""Shared dedicated PostgreSQL boundary; ADR-002/013; no connection discovery."""

from sqlalchemy import text
from sqlalchemy.engine import Connection


class DatabaseBoundaryError(ValueError):
    """A persistence boundary failure without credentials or private values."""


def require_transaction(connection: Connection) -> None:
    """The caller owns commit/rollback; state and audit changes must commit together."""
    if not connection.in_transaction():
        raise DatabaseBoundaryError("Persistence requires an explicit caller-owned transaction.")


def validate_application_connection(connection: Connection) -> None:
    """Reject migration/admin sessions and other databases before accessing application state."""
    require_transaction(connection)
    identity = connection.execute(
        text("SELECT current_database(), session_user, current_user")
    ).one()
    if tuple(identity) != ("acoa", "acoa_app", "acoa_app"):
        raise DatabaseBoundaryError("Persistence requires the authenticated ACOA application role.")
