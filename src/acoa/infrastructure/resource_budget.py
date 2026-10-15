"""Shared exact-money holds for external and model operation identities."""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from acoa.infrastructure.postgres import DatabaseBoundaryError, require_transaction


def register_resource_attempt(connection: Connection, attempt_id: UUID, kind: str) -> None:
    require_transaction(connection)
    if kind not in ("external", "model"):
        raise DatabaseBoundaryError("Resource attempt kind must be explicit.")
    connection.execute(
        text("""INSERT INTO acoa.resource_attempts
        (attempt_id,kind,external_attempt_id,model_call_id) VALUES
        (:id,:kind,CASE WHEN :kind='external' THEN :id END,CASE WHEN :kind='model' THEN :id END)
        ON CONFLICT (attempt_id) DO NOTHING"""),
        {"id": attempt_id, "kind": kind},
    )
    stored: str = connection.execute(
        text("SELECT kind FROM acoa.resource_attempts WHERE attempt_id=:id"), {"id": attempt_id}
    ).scalar_one()
    if stored != kind:
        raise DatabaseBoundaryError("A resource identity cannot be reused across operation kinds.")
