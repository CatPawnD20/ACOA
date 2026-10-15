"""Restart-safe mailbox polling orchestration; EP-06.02."""

from collections.abc import Callable
from datetime import datetime
from typing import Protocol
from uuid import UUID, uuid4

from acoa.application.mail import MailChangeProvider
from acoa.domain.mail import (
    MailboxCheckpoint,
    MailChange,
    MailCursorExpired,
    MailSyncResult,
    MailSyncStatus,
    require_provider_name,
)
from acoa.domain.values import DomainError, require_identifier, require_timestamp


class MailSyncStore(Protocol):
    def load_checkpoint(self, account_id: UUID, provider: str) -> MailboxCheckpoint | None: ...

    def reconcile(
        self,
        checkpoint: MailboxCheckpoint,
        final_cursor: str,
        changes: tuple[MailChange, ...],
        sync_id: UUID,
        started_at: datetime,
        completed_at: datetime,
    ) -> MailSyncResult: ...

    def record_full_sync_required(self, result: MailSyncResult) -> None: ...


def _require_poll_bounds(page_size: int, max_pages: int) -> None:
    for value, maximum, name in (
        (page_size, 500, "page size"),
        (max_pages, 100, "page count"),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
            raise DomainError(f"Mail polling {name} is outside its bounded contract.")


def _merge_changes(collected: dict[str, MailChange], changes: tuple[MailChange, ...]) -> None:
    for change in changes:
        prior = collected.get(change.provider_event_id)
        if prior is not None and prior != change:
            raise DomainError("A provider event identity changed during mailbox polling.")
        collected[change.provider_event_id] = change


def _full_sync_required(
    sync_id: UUID,
    account_id: UUID,
    provider: str,
    start_cursor: str | None,
    started_at: datetime,
    completed_at: datetime,
) -> MailSyncResult:
    return MailSyncResult(
        sync_id=sync_id,
        account_id=account_id,
        provider=provider,
        status=MailSyncStatus.FULL_SYNC_REQUIRED,
        start_cursor=start_cursor,
        final_cursor=None,
        fetched_count=0,
        inserted_count=0,
        started_at=started_at,
        completed_at=completed_at,
    )


def _record_full_sync_required(
    store: MailSyncStore,
    sync_id: UUID,
    account_id: UUID,
    provider: str,
    start_cursor: str | None,
    started_at: datetime,
    completed_at: datetime,
) -> MailSyncResult:
    result = _full_sync_required(
        sync_id,
        account_id,
        provider,
        start_cursor,
        started_at,
        completed_at,
    )
    store.record_full_sync_required(result)
    return result


def sync_mailbox(
    account_id: UUID,
    provider_name: str,
    provider: MailChangeProvider,
    store: MailSyncStore,
    clock: Callable[[], datetime],
    *,
    page_size: int = 100,
    max_pages: int = 20,
) -> MailSyncResult:
    """Fetch every bounded page, then atomically record events and advance the cursor."""
    require_identifier(account_id)
    require_provider_name(provider_name)
    if not callable(clock):
        raise DomainError("Mailbox polling requires an explicit clock.")
    started_at = clock()
    require_timestamp(started_at)
    _require_poll_bounds(page_size, max_pages)
    sync_id = uuid4()
    checkpoint = store.load_checkpoint(account_id, provider_name)
    if checkpoint is None:
        return _record_full_sync_required(
            store, sync_id, account_id, provider_name, None, started_at, clock()
        )

    page_token: str | None = None
    seen_page_tokens: set[str] = set()
    changes: dict[str, MailChange] = {}
    final_cursor = checkpoint.cursor
    try:
        for _ in range(max_pages):
            delta = provider.list_changes(checkpoint.cursor, page_token, page_size)
            _merge_changes(changes, delta.changes)
            final_cursor = delta.checkpoint_cursor
            page_token = delta.next_page_token
            if page_token is None:
                break
            if page_token in seen_page_tokens:
                raise DomainError("Mailbox polling returned a repeated page token.")
            seen_page_tokens.add(page_token)
        else:
            raise DomainError("Mailbox polling exceeded its maximum page count.")
    except MailCursorExpired:
        return _record_full_sync_required(
            store,
            sync_id,
            account_id,
            provider_name,
            checkpoint.cursor,
            started_at,
            clock(),
        )

    completed_at = clock()
    require_timestamp(completed_at)
    if completed_at < started_at:
        raise DomainError("Mailbox polling cannot complete before it starts.")
    return store.reconcile(
        checkpoint,
        final_cursor,
        tuple(changes.values()),
        sync_id,
        started_at,
        completed_at,
    )
