#!/bin/sh
# Offline PostgreSQL + artifact recovery bundle for EP-10.02.
set -eu
umask 077

fail() {
    echo "recovery failed: $1" >&2
    exit 1
}

require_backup_id() {
    case "${1:-}" in
        ''|*[!a-zA-Z0-9._-]*) fail "backup ID must use safe filename characters" ;;
    esac
}

connect() {
    IFS= read -r PGPASSWORD < /run/secrets/postgres_migration_password
    export PGPASSWORD
}

disconnect() {
    unset PGPASSWORD
}

database_value() {
    psql --no-psqlrc --set ON_ERROR_STOP=1 --tuples-only --no-align --command "$1"
}

verify_bundle() {
    bundle=$1
    [ -f "$bundle/database.dump" ] || fail "database dump is missing"
    [ -f "$bundle/artifacts.tar" ] || fail "artifact archive is missing"
    [ -f "$bundle/SHA256SUMS" ] || fail "checksum manifest is missing"
    [ -f "$bundle/metadata" ] || fail "bundle metadata is missing"
    (cd "$bundle" && sha256sum --check --strict SHA256SUMS) >/dev/null \
        || fail "bundle checksum verification failed"
    grep -qx 'schema=acoa-recovery-bundle/1' "$bundle/metadata" \
        || fail "bundle schema is unsupported"
    grep -Eq '^migration_head=[a-zA-Z0-9_]+$' "$bundle/metadata" \
        || fail "migration head metadata is invalid"
}

verify_restored_artifacts() {
    [ -z "$(find /artifacts -type l -print -quit)" ] || fail "artifact tree contains a link"
    [ -z "$(find /artifacts ! -type f ! -type d -print -quit)" ] \
        || fail "artifact tree contains an unsupported object"
    expected_count=$(database_value "SELECT count(*) FROM acoa.application_artifacts")
    actual_count=$(find /artifacts -type f | wc -l | tr -d ' ')
    [ "$actual_count" = "$expected_count" ] || fail "artifact file count does not match database"
    database_value "SELECT storage_key || E'\\t' || content_sha256 || E'\\t' || content_size
                    FROM acoa.application_artifacts ORDER BY storage_key" > /tmp/artifacts.index
    while IFS="$(printf '\t')" read -r key expected_hash expected_size; do
        case "$key" in
            artifacts/*) ;;
            *) fail "database contains an unsafe artifact key" ;;
        esac
        case "$key" in *[!a-zA-Z0-9._/-]*) fail "database contains an unsafe artifact key" ;; esac
        case "$key" in *'/../'*|../*|*/..|*'//'*) fail "database contains an unsafe artifact key" ;; esac
        file="/artifacts/$key"
        [ -f "$file" ] && [ ! -L "$file" ] || fail "a restored artifact is missing"
        actual_size=$(wc -c < "$file" | tr -d ' ')
        actual_hash=$(sha256sum "$file" | cut -d ' ' -f 1)
        [ "$actual_size" = "$expected_size" ] || fail "a restored artifact size is invalid"
        [ "$actual_hash" = "$expected_hash" ] || fail "a restored artifact hash is invalid"
    done < /tmp/artifacts.index
}

verify_target() {
    bundle=$1
    restored_head=$(database_value "SELECT version_num FROM acoa_migrations.alembic_version")
    expected_head=$(sed -n 's/^migration_head=//p' "$bundle/metadata")
    [ "$restored_head" = "$expected_head" ] || fail "restored migration head is invalid"
    verify_restored_artifacts
}

backup() {
    require_backup_id "$1"
    destination="/backups/$1"
    [ ! -e "$destination" ] || fail "backup destination already exists"
    mkdir -m 700 "$destination"
    connect
    migration_head=$(database_value "SELECT version_num FROM acoa_migrations.alembic_version")
    [ -n "$migration_head" ] || fail "migration head is unavailable"
    verify_restored_artifacts
    pg_dump --format=custom --no-owner --schema=acoa --schema=acoa_migrations \
        --serializable-deferrable --file="$destination/database.dump"
    disconnect
    tar --create --file="$destination/artifacts.tar" --directory=/artifacts .
    created_at=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
    {
        echo 'schema=acoa-recovery-bundle/1'
        echo "backup_id=$1"
        echo "created_at=$created_at"
        echo "migration_head=$migration_head"
    } > "$destination/metadata"
    (cd "$destination" && sha256sum database.dump artifacts.tar metadata > SHA256SUMS)
    verify_bundle "$destination"
    echo "recovery backup verified: $1"
}

restore() {
    require_backup_id "$1"
    source="/backups/$1"
    verify_bundle "$source"
    [ -z "$(find /artifacts -mindepth 1 -print -quit)" ] \
        || fail "artifact target must be empty"
    connect
    table_count=$(database_value "SELECT count(*) FROM information_schema.tables
        WHERE table_schema IN ('acoa','acoa_migrations')")
    [ "$table_count" = 0 ] || fail "database target must contain no application tables"
    pg_restore --list "$source/database.dump" > /tmp/restore.list
    grep -v -E ' SCHEMA - (acoa|acoa_migrations) ' /tmp/restore.list > /tmp/restore-existing-schemas.list
    pg_restore --exit-on-error --no-owner --use-list=/tmp/restore-existing-schemas.list \
        --dbname=acoa "$source/database.dump"
    psql --no-psqlrc --set ON_ERROR_STOP=1 <<'SQL'
GRANT USAGE ON SCHEMA acoa TO acoa_app;
REVOKE ALL ON SCHEMA acoa_migrations FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE acoa_migrator IN SCHEMA acoa
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO acoa_app;
ALTER DEFAULT PRIVILEGES FOR ROLE acoa_migrator IN SCHEMA acoa
    GRANT USAGE, SELECT ON SEQUENCES TO acoa_app;
SQL
    tar --extract --file="$source/artifacts.tar" --directory=/artifacts
    verify_target "$source"
    disconnect
    echo "recovery restore verified: $1"
}

audit() {
    require_backup_id "$1"
    source="/backups/$1"
    verify_bundle "$source"
    connect
    verify_target "$source"
    disconnect
    echo "recovery target verified: $1"
}

case "${1:-help}" in
    backup) [ "$#" = 2 ] || fail "usage: recovery.sh backup BACKUP_ID"; backup "$2" ;;
    restore) [ "$#" = 2 ] || fail "usage: recovery.sh restore BACKUP_ID"; restore "$2" ;;
    verify) [ "$#" = 2 ] || fail "usage: recovery.sh verify BACKUP_ID"; verify_bundle "/backups/$2" ;;
    audit) [ "$#" = 2 ] || fail "usage: recovery.sh audit BACKUP_ID"; audit "$2" ;;
    help) echo 'usage: recovery.sh {backup|restore|verify|audit} BACKUP_ID' ;;
    *) fail "unsupported recovery command" ;;
esac
