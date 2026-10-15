"""Atomic PostgreSQL mailbox cursor and provider-event reconciliation."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping

from acoa.domain.mail import (
    MailboxCheckpoint,
    MailChange,
    MailDelta,
    MailSyncResult,
    MailSyncStatus,
    mail_change_sha256,
    mail_sync_result_sha256,
    require_provider_name,
)
from acoa.domain.values import require_identifier, require_timestamp
from acoa.infrastructure.postgres import DatabaseBoundaryError, validate_application_connection


class MailSyncRepository:
    def __init__(self, connection: Connection) -> None:
        validate_application_connection(connection)
        self.connection = connection

    def load_checkpoint(self, account_id: UUID, provider: str) -> MailboxCheckpoint | None:
        require_identifier(account_id)
        require_provider_name(provider)
        row = (
            self.connection.execute(
                text("""SELECT account_id,provider,cursor,revision,updated_at
                    FROM acoa.mailbox_sync_state
                    WHERE account_id=:account AND provider=:provider"""),
                {"account": account_id, "provider": provider},
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else self._checkpoint_from_row(row)

    def initialize_checkpoint(self, checkpoint: MailboxCheckpoint) -> None:
        """Record the cursor produced by a separately verified full synchronization."""
        if not isinstance(checkpoint, MailboxCheckpoint):
            raise DatabaseBoundaryError("A validated mailbox checkpoint is required.")
        inserted = self.connection.execute(
            text("""INSERT INTO acoa.mailbox_sync_state
                (account_id,provider,cursor,revision,updated_at)
                VALUES (:account,:provider,:cursor,:revision,:updated_at)
                ON CONFLICT (account_id,provider) DO NOTHING RETURNING account_id"""),
            {
                "account": checkpoint.account_id,
                "provider": checkpoint.provider,
                "cursor": checkpoint.cursor,
                "revision": checkpoint.revision,
                "updated_at": checkpoint.updated_at,
            },
        ).scalar_one_or_none()
        if inserted is not None:
            return
        if self.load_checkpoint(checkpoint.account_id, checkpoint.provider) != checkpoint:
            raise DatabaseBoundaryError("A mailbox checkpoint can only be initialized once.")

    def reconcile(
        self,
        checkpoint: MailboxCheckpoint,
        final_cursor: str,
        changes: tuple[MailChange, ...],
        sync_id: UUID,
        started_at: datetime,
        completed_at: datetime,
    ) -> MailSyncResult:
        if not isinstance(checkpoint, MailboxCheckpoint):
            raise DatabaseBoundaryError("A validated mailbox checkpoint is required.")
        MailDelta(changes, final_cursor)
        require_identifier(sync_id)
        require_timestamp(started_at)
        require_timestamp(completed_at)
        if completed_at < started_at:
            raise DatabaseBoundaryError("Mailbox reconciliation cannot complete before it starts.")
        if self._lock_checkpoint(checkpoint) != checkpoint:
            raise DatabaseBoundaryError("The mailbox cursor advanced in another transaction.")

        inserted_count = sum(
            self._record_change(checkpoint, final_cursor, change, sync_id, completed_at)
            for change in changes
        )
        result = MailSyncResult(
            sync_id=sync_id,
            account_id=checkpoint.account_id,
            provider=checkpoint.provider,
            status=MailSyncStatus.COMPLETED,
            start_cursor=checkpoint.cursor,
            final_cursor=final_cursor,
            fetched_count=len(changes),
            inserted_count=inserted_count,
            started_at=started_at,
            completed_at=completed_at,
        )
        self._advance_checkpoint(checkpoint, final_cursor, completed_at)
        self._record_result(result)
        return result

    def _lock_checkpoint(self, checkpoint: MailboxCheckpoint) -> MailboxCheckpoint | None:
        row = (
            self.connection.execute(
                text("""SELECT account_id,provider,cursor,revision,updated_at
                    FROM acoa.mailbox_sync_state
                    WHERE account_id=:account AND provider=:provider FOR UPDATE"""),
                {"account": checkpoint.account_id, "provider": checkpoint.provider},
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else self._checkpoint_from_row(row)

    @staticmethod
    def _checkpoint_from_row(row: RowMapping) -> MailboxCheckpoint:
        return MailboxCheckpoint(
            account_id=row["account_id"],
            provider=row["provider"],
            cursor=row["cursor"],
            revision=row["revision"],
            updated_at=row["updated_at"],
        )

    def _record_change(
        self,
        checkpoint: MailboxCheckpoint,
        final_cursor: str,
        change: MailChange,
        sync_id: UUID,
        recorded_at: datetime,
    ) -> int:
        digest = mail_change_sha256(checkpoint.account_id, checkpoint.provider, change)
        inserted = self.connection.execute(
            text("""INSERT INTO acoa.mailbox_events
                (account_id,provider,provider_event_id,provider_message_id,
                 provider_thread_id,kind,observed_cursor,sync_id,recorded_at,record_sha256)
                VALUES (:account,:provider,:event,:message,:thread,:kind,:cursor,
                    :sync,:recorded_at,:digest)
                ON CONFLICT (account_id,provider,provider_event_id) DO NOTHING
                RETURNING provider_event_id"""),
            {
                "account": checkpoint.account_id,
                "provider": checkpoint.provider,
                "event": change.provider_event_id,
                "message": change.message.provider_message_id,
                "thread": change.message.provider_thread_id,
                "kind": change.kind.value,
                "cursor": final_cursor,
                "sync": sync_id,
                "recorded_at": recorded_at,
                "digest": digest,
            },
        ).scalar_one_or_none()
        if inserted is not None:
            return 1
        prior = self.connection.execute(
            text("""SELECT record_sha256 FROM acoa.mailbox_events
                WHERE account_id=:account AND provider=:provider AND provider_event_id=:event"""),
            {
                "account": checkpoint.account_id,
                "provider": checkpoint.provider,
                "event": change.provider_event_id,
            },
        ).scalar_one_or_none()
        if prior != digest:
            raise DatabaseBoundaryError("A provider mail event identity changed its content.")
        return 0

    def _advance_checkpoint(
        self, checkpoint: MailboxCheckpoint, final_cursor: str, completed_at: datetime
    ) -> None:
        updated = self.connection.execute(
            text("""UPDATE acoa.mailbox_sync_state
                SET cursor=:cursor,revision=revision+1,updated_at=:updated_at
                WHERE account_id=:account AND provider=:provider AND revision=:revision"""),
            {
                "cursor": final_cursor,
                "updated_at": completed_at,
                "account": checkpoint.account_id,
                "provider": checkpoint.provider,
                "revision": checkpoint.revision,
            },
        ).rowcount
        if updated != 1:
            raise DatabaseBoundaryError("The mailbox checkpoint update lost its cursor fence.")

    def record_full_sync_required(self, result: MailSyncResult) -> None:
        if (
            not isinstance(result, MailSyncResult)
            or result.status is not MailSyncStatus.FULL_SYNC_REQUIRED
        ):
            raise DatabaseBoundaryError("A full-sync requirement result is required.")
        self._record_result(result)

    def _record_result(self, result: MailSyncResult) -> None:
        if not isinstance(result, MailSyncResult):
            raise DatabaseBoundaryError("A validated mail sync result is required.")
        inserted = self.connection.execute(
            text("""INSERT INTO acoa.mailbox_sync_runs
                (sync_id,account_id,provider,status,start_cursor,final_cursor,
                 fetched_count,inserted_count,started_at,completed_at,record_sha256)
                VALUES (:sync,:account,:provider,:status,:start_cursor,:final_cursor,
                    :fetched,:inserted,:started_at,:completed_at,:digest)
                ON CONFLICT (sync_id) DO NOTHING RETURNING sync_id"""),
            {
                "sync": result.sync_id,
                "account": result.account_id,
                "provider": result.provider,
                "status": result.status.value,
                "start_cursor": result.start_cursor,
                "final_cursor": result.final_cursor,
                "fetched": result.fetched_count,
                "inserted": result.inserted_count,
                "started_at": result.started_at,
                "completed_at": result.completed_at,
                "digest": mail_sync_result_sha256(result),
            },
        ).scalar_one_or_none()
        if inserted is None:
            raise DatabaseBoundaryError("A mail sync ID must remain unique.")
