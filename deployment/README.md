# Dedicated ACOA PostgreSQL

EP-00.03; E-05/E-07/E-11; ADR-002/011/013.

## Start the local development service

Run from the repository root with Docker Desktop's Linux engine available:

```powershell
& .\.venv\Scripts\python.exe deployment/prepare_local.py
docker compose --env-file deployment/compose.env.example -p acoa-dev -f deployment/compose.yaml config --quiet
docker compose --env-file deployment/compose.env.example -p acoa-dev -f deployment/compose.yaml up -d --wait --wait-timeout 90
docker compose --env-file deployment/compose.env.example -p acoa-dev -f deployment/compose.yaml ps
```

On POSIX, use `.venv/bin/python`. The password generator uses only the Python
standard library, creates three independent random passwords, and preserves
existing files. It never prints or reads existing password values. Passwords live
in ignored `deployment/secrets/` files and are mounted read-only through Compose
secrets. They are not embedded in YAML, command arguments, or committed examples.
Compose explicitly reads the harmless example environment file rather than
discovering a real `.env` file. Shell environment variables still take precedence.

On POSIX, new secret directories/files request modes 0700/0600. Python's file
mode handling does not establish equivalent Windows ACL restrictions. On Windows,
keep the project in your private user directory and restrict its inherited ACLs
appropriately. Local Compose secrets are bind-mounted files, not an encrypted
secret vault. Docker administrators and processes with access to those files can
read them; do not use production credentials for local development.

## Resources and access

The base configuration uses the digest-pinned official PostgreSQL 18.6 trixie
image and creates:

- `acoa-dev-acoa-postgres-1`: dedicated PostgreSQL container;
- `acoa-dev_postgres-data`: dedicated persistent volume, mounted at
  `/var/lib/postgresql` for PostgreSQL 18's versioned data layout;
- `acoa-dev_database`: internal network with no host port published.

No existing database endpoint, credentials, network, or volume is reused. The
base file can be used unchanged on a cloud Docker host with separately provisioned
secret files and an explicit project name. It does not provision a cloud host.
There is no runnable API/worker image yet; those services belong to later tasks.
Start only one active deployment when moving environments (ADR-011).

For host tools during development, opt into the loopback-only overlay:

```powershell
docker compose --env-file deployment/compose.env.example -p acoa-dev -f deployment/compose.yaml -f deployment/compose.local.yaml up -d --wait --wait-timeout 90
```

It adds a separate project-scoped NAT bridge for host access and publishes
`127.0.0.1:15432` by default. This optional bridge permits outbound connectivity
from the database container; use the internal-only base for container-based
application access. The nonsecret
`ACOA_POSTGRES_PORT` setting can select another free port. Reapply the base command
to recreate the container without the published port; its named volume persists.
Keep the same explicit project name and Compose files for subsequent operations.

## Role boundaries

| Role | Purpose | Privileges |
|---|---|---|
| `acoa_admin` | Bootstrap and explicit maintenance | Cluster superuser; never an application credential |
| `acoa_migrator` | Explicit migrations | Owns `acoa` and `acoa_migrations`; no superuser, role creation, or database creation |
| `acoa_app` | Later application runtime | Connect, schema usage, table CRUD, sequence usage/select; no DDL or migration-role membership |

The database is named `acoa`. Public database privileges and public-schema
privileges are revoked for this database. Default privileges grant application
access to tables/sequences created **by `acoa_migrator` in schema `acoa`**. Future
migrations must use that role/schema for application objects. The version table is
isolated in `acoa_migrations`, with no application-role access. Other owners
do not inherit those default grants. Security-sensitive table permissions and
function EXECUTE permissions must be reviewed when those objects are introduced.

TCP authentication requires SCRAM passwords. Unix-socket access inside the
container uses the official image's local trust behavior; Docker exec is therefore
an administrative boundary. A health check uses `pg_isready` for server readiness;
it is not proof that an application's password or privileges are valid.

The initialization script runs only for an **empty** database volume. It creates
roles/schemas atomically and fails on SQL errors. It creates no business tables or
Alembic revision. Application adapters and business revisions remain later work.
Changing secret files does not rotate passwords in an initialized database.
Existing incomplete/invalid secret files are preserved, not silently replaced.
Diagnose startup errors and perform deliberate credential rotation when needed.

## Explicit migrations

The [migration runner](migrate.py) and [pinned tool requirements](migration-requirements.txt)
provide G0 migration infrastructure. There are no business revisions yet. An empty
`upgrade head` creates only Alembic's empty version table in `acoa_migrations`.

Use the one-shot maintenance container to keep the database port unpublished:

```powershell
docker compose --env-file deployment/compose.env.example -p acoa-dev -f deployment/compose.yaml build acoa-migrate
docker compose --env-file deployment/compose.env.example -p acoa-dev -f deployment/compose.yaml run --rm --no-deps acoa-migrate current
docker compose --env-file deployment/compose.env.example -p acoa-dev -f deployment/compose.yaml run --rm --no-deps acoa-migrate upgrade
```

Start the database with the base `up` command first. The `maintenance` profile
prevents the runner from starting during normal `up`. `heads`, `history`, and
`upgrade --sql` can be supplied instead of `current`; offline SQL does not read
the password or open a database connection. Build inputs are allowlisted by
[`.dockerignore`](.dockerignore), excluding local secret files. Execution is on
the internal ACOA network with only the migration password, a read-only filesystem,
temporary `/tmp`, no capabilities and no-new-privileges. The container is removed
when its command exits. The image can be transferred to another Docker host with
the corresponding dedicated PostgreSQL deployment and secret provisioning.
No cloud deployment was performed.

For host execution, explicitly install the tools and use the local port overlay:

```powershell
& .\.venv\Scripts\python.exe -m pip --isolated install --index-url https://pypi.org/simple -r deployment/migration-requirements.txt
& .\.venv\Scripts\python.exe deployment/migrate.py current --password-file deployment/secrets/postgres_migration_password
& .\.venv\Scripts\python.exe deployment/migrate.py upgrade --password-file deployment/secrets/postgres_migration_password
```

Host defaults are `127.0.0.1:15432`; use `--host`/`--port` only to explicitly select
your dedicated ACOA server. The database and user are fixed; target identity,
schema ownership and privilege checks run before Alembic. Credentials and driver
exceptions are not printed. The runner does not discover `.env` files or credential
URLs. There is no automatic retry, downgrade or revision generation command.

An existing EP-00.03 volume created before the migration follow-up lacks the new
metadata schema. The follow-up prepared the verified local development volume;
other existing deployments need an explicitly authorized maintenance step creating
`acoa_migrations` owned by `acoa_migrator` and revoking PUBLIC access. Do not reset
an existing volume or rerun the full role initializer to obtain it. See
[the migration verification record](../tasks/EP-00.03-migration-runner.md).

## Stop, preservation, and backup boundaries

```powershell
docker compose --env-file deployment/compose.env.example -p acoa-dev -f deployment/compose.yaml stop
```

Stopping or recreating this container preserves its named volume. `down` also
preserves the volume unless `--volumes` is supplied. Do not use volume deletion,
Docker prune, factory reset, or automatic fresh-volume recovery on retained data.

Backups belong only to this dedicated service. Use `pg_dump` in custom format for
the `acoa` database and retain the image digest, schema/migration version, and
secret provisioning/role inventory separately in protected storage. Restore into
a new isolated ACOA deployment with the same role names, verify ownership, grants,
data and artifact integrity, then deliberately switch the single active deployment.
Never restore into an unrelated project's database or an existing active database
as part of a routine development check. Backup/restore automation and a recovery
exercise are not implemented in EP-00.03.

## Verified behavior and limits

See [the task record](../tasks/EP-00.03-postgresql.md) for actual checks and platform
limits. No live sending or policy authorization is enabled by starting PostgreSQL.

Official references: [PostgreSQL image](https://hub.docker.com/_/postgres),
[Compose secrets](https://docs.docker.com/compose/how-tos/use-secrets/),
[internal networks](https://docs.docker.com/reference/compose-file/networks/), and
[default privileges](https://www.postgresql.org/docs/18/sql-alterdefaultprivileges.html).
