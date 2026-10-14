"""Alembic environment: G0; E-05/E-07; ADR-002/013."""

from alembic import context
from sqlalchemy.engine import Connection


def run_offline_migrations() -> None:
    """Render PostgreSQL SQL without credentials or a database connection."""
    context.configure(
        dialect_name="postgresql",
        target_metadata=None,
        literal_binds=True,
        version_table_schema="acoa_migrations",
    )
    with context.begin_transaction():
        context.run_migrations()


def run_online_migrations() -> None:
    """Use only the connection validated and supplied by the explicit runner."""
    connection = context.config.attributes.get("connection")
    if not isinstance(connection, Connection):
        raise RuntimeError("Online migrations require the validated migration runner.")
    context.configure(
        connection=connection,
        target_metadata=None,
        version_table_schema="acoa_migrations",
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_offline_migrations()
else:
    run_online_migrations()
