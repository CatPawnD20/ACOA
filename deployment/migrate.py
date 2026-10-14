"""Explicit PostgreSQL migration runner: G0; E-05/E-07/E-11; ADR-002/011/013."""

import argparse
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.util.exc import CommandError
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Connection, ScalarResult
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool

DEFAULT_LOCAL_PORT = 15432
CONNECTION_TIMEOUT_SECONDS = 5


class MigrationError(ValueError):
    """A runner validation error with no credential or target values."""


def read_migration_password(path: Path) -> str:
    """Read only the explicitly selected file, without exposing its contents."""
    try:
        password = path.read_text(encoding="utf-8").rstrip("\r\n")
    except (OSError, UnicodeError):
        raise MigrationError("Cannot read the migration password file.") from None
    if not password or any(character in password for character in "\r\n\0"):
        raise MigrationError("The migration password file must contain one nonempty value.")
    return password


def build_migration_url(host: str, port: int, password_file: Path) -> URL:
    """Select the dedicated database and migration role without URL interpolation."""
    if not host or host != host.strip() or any(character.isspace() for character in host):
        raise MigrationError("The database host must be a nonempty hostname or address.")
    if not 1 <= port <= 65535:
        raise MigrationError("The database port must be between 1 and 65535.")
    return URL.create(
        "postgresql+psycopg",
        username="acoa_migrator",
        password=read_migration_password(password_file),
        host=host,
        port=port,
        database="acoa",
    )


def validate_target_identity(connection: Connection) -> None:
    """Require the dedicated database and authenticated migration role."""
    identity = connection.execute(text("SELECT current_database(), current_user")).one()
    if tuple(identity) != ("acoa", "acoa_migrator"):
        raise MigrationError("The connection is not the dedicated ACOA migration target.")


def validate_schema_ownership(connection: Connection) -> None:
    """Require both dedicated schemas to be owned by the authenticated role."""
    owned_schemas: ScalarResult[str] = connection.execute(
        text(
            "SELECT n.nspname FROM pg_namespace n JOIN pg_roles r ON r.oid = n.nspowner "
            "WHERE n.nspname IN ('acoa', 'acoa_migrations') AND r.rolname = current_user"
        )
    ).scalars()
    if set(owned_schemas) != {"acoa", "acoa_migrations"}:
        raise MigrationError("The dedicated migration schemas are missing or have another owner.")


def validate_role_privileges(connection: Connection) -> None:
    """Enforce migration least privilege and the application's metadata boundary."""
    is_privileged: bool = connection.execute(
        text(
            "SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls "
            "FROM pg_roles WHERE rolname = current_user"
        )
    ).scalar_one()
    if is_privileged:
        raise MigrationError("The migration role must not have cluster administrative privileges.")
    app_has_metadata_access: bool = connection.execute(
        text(
            "SELECT has_schema_privilege('acoa_app', 'acoa_migrations', 'USAGE') OR "
            "has_schema_privilege('acoa_app', 'acoa_migrations', 'CREATE')"
        )
    ).scalar_one()
    if app_has_metadata_access:
        raise MigrationError("The application role must not access migration metadata.")


def validate_migration_target(connection: Connection) -> None:
    """Validate identity, schema ownership and role boundaries before Alembic runs."""
    validate_target_identity(connection)
    validate_schema_ownership(connection)
    validate_role_privileges(connection)


def run_online_command(config: Config, url: URL, operation: str) -> None:
    """Own connection/transaction lifetime and invoke the selected migration operation."""
    engine = create_engine(
        url,
        poolclass=NullPool,
        hide_parameters=True,
        echo=False,
        connect_args={"connect_timeout": CONNECTION_TIMEOUT_SECONDS},
    )
    try:
        with engine.begin() as connection:
            validate_migration_target(connection)
            config.attributes["connection"] = connection
            if operation == "upgrade":
                command.upgrade(config, "head")
            else:
                command.current(config)
    finally:
        config.attributes.pop("connection", None)
        engine.dispose()


def run_command(args: argparse.Namespace) -> None:
    """Separate local graph/offline operations from authenticated database operations."""
    config = Config(str(Path(__file__).resolve().parent / "alembic.ini"))
    if args.sql:
        if args.operation != "upgrade":
            raise MigrationError("SQL output is supported only for upgrade.")
        command.upgrade(config, "head", sql=True)
        return
    if args.operation == "heads":
        command.heads(config)
        return
    if args.operation == "history":
        command.history(config)
        return
    if args.password_file is None:
        raise MigrationError("Online commands require an explicit migration password file.")
    url = build_migration_url(args.host, args.port, args.password_file)
    run_online_command(config, url, args.operation)


def parse_arguments() -> argparse.Namespace:
    """Expose only supported bootstrap commands and explicit target selection."""
    parser = argparse.ArgumentParser(description="Run ACOA PostgreSQL migrations explicitly.")
    parser.add_argument("operation", choices=("current", "upgrade", "heads", "history"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_LOCAL_PORT)
    parser.add_argument("--password-file", type=Path)
    parser.add_argument("--sql", action="store_true")
    return parser.parse_args()


def main() -> int:
    """Report controlled failures without printing driver exceptions or secret values."""
    try:
        run_command(parse_arguments())
    except MigrationError as error:
        print(str(error), file=sys.stderr)
        return 1
    except (SQLAlchemyError, CommandError):
        print(
            "Migration failed; check database readiness, credentials and revisions.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
