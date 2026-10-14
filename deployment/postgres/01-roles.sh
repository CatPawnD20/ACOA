#!/bin/sh
# EP-00.03: E-05/E-07; ADR-002/013. Only runs on an empty database volume.
set -eu

ACOA_MIGRATION_PASSWORD="$(cat /run/secrets/postgres_migration_password)"
ACOA_APP_PASSWORD="$(cat /run/secrets/postgres_app_password)"
export ACOA_MIGRATION_PASSWORD ACOA_APP_PASSWORD

psql --no-psqlrc --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    --set ON_ERROR_STOP=1 <<'SQL'
\getenv migration_password ACOA_MIGRATION_PASSWORD
\getenv app_password ACOA_APP_PASSWORD
BEGIN;
CREATE ROLE acoa_migrator LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
    NOREPLICATION NOBYPASSRLS PASSWORD :'migration_password';
CREATE ROLE acoa_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
    NOREPLICATION NOBYPASSRLS PASSWORD :'app_password';
REVOKE ALL ON DATABASE acoa FROM PUBLIC;
GRANT CONNECT ON DATABASE acoa TO acoa_migrator, acoa_app;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
CREATE SCHEMA acoa AUTHORIZATION acoa_migrator;
CREATE SCHEMA acoa_migrations AUTHORIZATION acoa_migrator;
REVOKE ALL ON SCHEMA acoa_migrations FROM PUBLIC;
GRANT USAGE ON SCHEMA acoa TO acoa_app;
ALTER ROLE acoa_migrator IN DATABASE acoa SET search_path = acoa;
ALTER ROLE acoa_app IN DATABASE acoa SET search_path = acoa;
ALTER DEFAULT PRIVILEGES FOR ROLE acoa_migrator IN SCHEMA acoa
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO acoa_app;
ALTER DEFAULT PRIVILEGES FOR ROLE acoa_migrator IN SCHEMA acoa
    GRANT USAGE, SELECT ON SEQUENCES TO acoa_app;
COMMIT;
SQL

unset ACOA_MIGRATION_PASSWORD ACOA_APP_PASSWORD
