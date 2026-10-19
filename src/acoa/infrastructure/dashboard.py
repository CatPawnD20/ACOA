"""Privacy-limited PostgreSQL projections for the EP-07 dashboard."""

from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from typing import cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine, RowMapping

from acoa.application.dashboard import (
    DashboardApplication,
    DashboardAuditEvent,
    DashboardAuthority,
    DashboardCompany,
    DashboardCost,
    DashboardDailyReport,
    DashboardNotification,
    DashboardPerformance,
    DashboardQuery,
    DashboardSnapshot,
    DashboardTask,
    DashboardWaitingItem,
)
from acoa.infrastructure.policy_authority import decode_authority
from acoa.infrastructure.postgres import validate_application_connection


class DashboardRepository:
    """Build a bounded user view without exposing stored JSON payloads or evidence."""

    def __init__(self, connection: Connection) -> None:
        validate_application_connection(connection)
        self.connection = connection

    def load(self, query: DashboardQuery | None = None) -> DashboardSnapshot:
        if query is None:
            query = DashboardQuery()
        elif not isinstance(query, DashboardQuery):
            raise ValueError("A validated dashboard query is required.")
        generated_at = cast(
            datetime, self.connection.execute(text("SELECT clock_timestamp()")).scalar_one()
        )
        return DashboardSnapshot(
            generated_at=generated_at,
            authority=self._authority(),
            applications=self._applications(query),
            companies=self._companies(query),
            tasks=self._tasks(query.limit),
            waiting_items=self._waiting_items(query.limit),
            costs=self._costs(),
            performance=self._performance(),
            audit_events=self._audit_events(query.limit),
            notifications=self._notifications(query.limit),
            daily_reports=self._daily_reports(min(query.limit, 30)),
        )

    @staticmethod
    def _masked_reference(identifier: UUID) -> str:
        """Return a stable local correlation label without exposing a stored identifier."""
        return f"ref-{sha256(identifier.bytes).hexdigest()[:12]}"

    def _audit_events(self, limit: int) -> tuple[DashboardAuditEvent, ...]:
        rows = self.connection.execute(
            text("""SELECT category,action,state,reference_id,recorded_at FROM (
                    SELECT 'task' category,'transition' action,new_state state,
                        task_id reference_id,recorded_at FROM acoa.task_events
                    UNION ALL
                    SELECT 'application','lifecycle',new_state,application_id,recorded_at
                        FROM acoa.application_events
                    UNION ALL
                    SELECT 'external_action','reconciliation',new_state,attempt_id,recorded_at
                        FROM acoa.reconciliation_events
                    UNION ALL
                    SELECT 'model','call',kind,call_id,recorded_at
                        FROM acoa.model_call_events
                    UNION ALL
                    SELECT 'dashboard','control',action,COALESCE(task_id,event_id),recorded_at
                        FROM acoa.dashboard_control_events
                ) event ORDER BY recorded_at DESC,reference_id LIMIT :limit"""),
            {"limit": limit},
        ).mappings()
        return tuple(
            DashboardAuditEvent(
                category=cast(str, row["category"]),
                action=cast(str, row["action"]),
                state=cast(str, row["state"]),
                reference=self._masked_reference(cast(UUID, row["reference_id"])),
                recorded_at=cast(datetime, row["recorded_at"]),
            )
            for row in rows
        )

    def _notifications(self, limit: int) -> tuple[DashboardNotification, ...]:
        rows = self.connection.execute(
            text("""SELECT notification.kind,notification.urgency,notification.state,
                    notification.application_id,notification.created_at
                FROM acoa.notification_items notification
                ORDER BY notification.created_at DESC,notification.notification_id
                LIMIT :limit"""),
            {"limit": limit},
        ).mappings()
        return tuple(
            DashboardNotification(
                kind=cast(str, row["kind"]),
                urgency=cast(str, row["urgency"]),
                state=cast(str, row["state"]),
                application_reference=self._masked_reference(cast(UUID, row["application_id"])),
                created_at=cast(datetime, row["created_at"]),
            )
            for row in rows
        )

    def _daily_reports(self, limit: int) -> tuple[DashboardDailyReport, ...]:
        rows = self.connection.execute(
            text("""SELECT window_start,window_end,created_at,incoming_count,
                    classified_count,immediate_count,reply_draft_count,followup_draft_count
                FROM acoa.mail_daily_digests
                ORDER BY window_end DESC,digest_id LIMIT :limit"""),
            {"limit": limit},
        ).mappings()
        return tuple(
            DashboardDailyReport(
                window_start=cast(datetime, row["window_start"]),
                window_end=cast(datetime, row["window_end"]),
                created_at=cast(datetime, row["created_at"]),
                incoming_count=cast(int, row["incoming_count"]),
                classified_count=cast(int, row["classified_count"]),
                immediate_count=cast(int, row["immediate_count"]),
                reply_draft_count=cast(int, row["reply_draft_count"]),
                followup_draft_count=cast(int, row["followup_draft_count"]),
            )
            for row in rows
        )

    def _authority(self) -> DashboardAuthority:
        row = (
            self.connection.execute(
                text("SELECT revision,payload FROM acoa.policy_authority WHERE singleton")
            )
            .mappings()
            .one()
        )
        authority = decode_authority(row["payload"])
        settings = authority.settings
        return DashboardAuthority(
            revision=cast(int, row["revision"]),
            paused=authority.paused,
            dry_run=settings.dry_run,
            external_actions_enabled=settings.external_actions_enabled,
            applications_per_day=settings.applications.max_per_day,
            applications_per_week=settings.applications.max_per_week,
            outreach_per_company=settings.outreach.per_company_limit,
            outreach_per_contact=settings.outreach.per_contact_limit,
            currency=settings.budget.currency,
            currency_per_day=settings.budget.max_currency_per_day,
            currency_per_month=settings.budget.max_currency_per_month,
            tokens_per_task=settings.budget.max_tokens_per_task,
            seconds_per_task=settings.budget.max_time_per_task,
            paid_services_enabled=settings.budget.paid_services_enabled,
            progress_stall_timeout=settings.budget.progress_stall_timeout,
        )

    def _applications(self, query: DashboardQuery) -> tuple[DashboardApplication, ...]:
        rows = self.connection.execute(
            text("""SELECT application.application_id, series.company_id,
                    COALESCE(organization.canonical_domain, series.company_id::text) company_label,
                    series.kind, application.state, application.submission_state,
                    application.created_at
                FROM acoa.applications application
                JOIN acoa.application_series series ON series.series_id=application.series_id
                LEFT JOIN acoa.organizations organization
                    ON organization.organization_id=series.company_id
                WHERE (CAST(:search AS text) IS NULL OR
                    position(lower(CAST(:search AS text)) in
                        lower(application.application_id::text))>0 OR
                    position(lower(CAST(:search AS text)) in lower(COALESCE(
                        organization.canonical_domain,series.company_id::text)))>0)
                ORDER BY application.created_at DESC, application.application_id
                LIMIT :limit"""),
            {"search": query.search, "limit": query.limit},
        ).mappings()
        return tuple(self._application(row) for row in rows)

    @staticmethod
    def _application(row: RowMapping) -> DashboardApplication:
        return DashboardApplication(
            application_id=cast(UUID, row["application_id"]),
            company_id=cast(UUID, row["company_id"]),
            company_label=cast(str, row["company_label"]),
            kind=cast(str, row["kind"]),
            state=cast(str, row["state"]),
            submission_state=cast(str, row["submission_state"]),
            created_at=cast(datetime, row["created_at"]),
        )

    def _companies(self, query: DashboardQuery) -> tuple[DashboardCompany, ...]:
        rows = self.connection.execute(
            text("""WITH companies AS (
                    SELECT organization_id company_id,canonical_domain label
                    FROM acoa.organizations
                    UNION ALL
                    SELECT DISTINCT series.company_id,series.company_id::text
                    FROM acoa.application_series series
                    WHERE NOT EXISTS (SELECT 1 FROM acoa.organizations organization
                        WHERE organization.organization_id=series.company_id)
                )
                SELECT company.company_id,company.label,
                    count(application.application_id) application_count,
                    count(application.application_id) FILTER
                        (WHERE application.state='open') open_application_count
                FROM companies company
                LEFT JOIN acoa.application_series series ON series.company_id=company.company_id
                LEFT JOIN acoa.applications application
                    ON application.series_id=series.series_id
                WHERE (CAST(:search AS text) IS NULL OR
                    position(lower(CAST(:search AS text)) in lower(company.label))>0)
                GROUP BY company.company_id,company.label
                ORDER BY open_application_count DESC,application_count DESC,label
                LIMIT :limit"""),
            {"search": query.search, "limit": query.limit},
        ).mappings()
        return tuple(
            DashboardCompany(
                company_id=cast(UUID, row["company_id"]),
                label=cast(str, row["label"]),
                application_count=cast(int, row["application_count"]),
                open_application_count=cast(int, row["open_application_count"]),
            )
            for row in rows
        )

    def _tasks(self, limit: int) -> tuple[DashboardTask, ...]:
        rows = self.connection.execute(
            text("""SELECT task_id,kind,state,attempt_count,next_run_at,updated_at
                FROM acoa.task_runs ORDER BY updated_at DESC,task_id LIMIT :limit"""),
            {"limit": limit},
        ).mappings()
        return tuple(
            DashboardTask(
                task_id=cast(UUID, row["task_id"]),
                kind=cast(str, row["kind"]),
                state=cast(str, row["state"]),
                attempt_count=cast(int, row["attempt_count"]),
                next_run_at=cast(datetime, row["next_run_at"]),
                updated_at=cast(datetime, row["updated_at"]),
            )
            for row in rows
        )

    def _waiting_items(self, limit: int) -> tuple[DashboardWaitingItem, ...]:
        rows = self.connection.execute(
            text("""SELECT task_id,kind,waiting_question_id,updated_at
                FROM acoa.task_runs WHERE state='waiting_user'
                ORDER BY updated_at,task_id LIMIT :limit"""),
            {"limit": limit},
        ).mappings()
        return tuple(
            DashboardWaitingItem(
                task_id=cast(UUID, row["task_id"]),
                task_kind=cast(str, row["kind"]),
                question_id=cast(UUID, row["waiting_question_id"]),
                waiting_since=cast(datetime, row["updated_at"]),
            )
            for row in rows
        )

    def _costs(self) -> tuple[DashboardCost, ...]:
        rows = self.connection.execute(
            text("""SELECT currency,COALESCE(sum(consumed),0) consumed,
                    COALESCE(sum(reserved),0) reserved,
                    count(*) FILTER (WHERE settled_at IS NULL) unsettled_count
                FROM acoa.budget_ledger GROUP BY currency ORDER BY currency""")
        ).mappings()
        return tuple(
            DashboardCost(
                currency=cast(str, row["currency"]),
                consumed=cast(Decimal, row["consumed"]),
                reserved=cast(Decimal, row["reserved"]),
                unsettled_count=cast(int, row["unsettled_count"]),
            )
            for row in rows
        )

    def _performance(self) -> DashboardPerformance:
        row = (
            self.connection.execute(
                text("""SELECT
                (SELECT count(*) FROM acoa.applications) application_count,
                (SELECT count(*) FROM acoa.applications WHERE state='open')
                    open_application_count,
                (SELECT count(*) FROM acoa.task_runs) task_count,
                (SELECT count(*) FROM acoa.task_runs WHERE state='completed') completed_task_count,
                (SELECT count(*) FROM acoa.task_runs WHERE state='failed') failed_task_count,
                (SELECT count(*) FROM acoa.task_runs WHERE state='waiting_user')
                    waiting_user_count,
                (SELECT count(*) FROM acoa.model_calls) model_call_count,
                (SELECT COALESCE(sum(consumed_tokens),0) FROM acoa.model_calls)
                    consumed_tokens,
                (SELECT COALESCE(sum(consumed_seconds),0) FROM acoa.model_calls)
                    consumed_seconds,
                (SELECT count(*) FROM acoa.external_action_attempts WHERE state='verified')
                    verified_action_count,
                (SELECT count(*) FROM acoa.external_action_attempts WHERE state='unconfirmed')
                    unconfirmed_action_count""")
            )
            .mappings()
            .one()
        )
        return DashboardPerformance(
            application_count=cast(int, row["application_count"]),
            open_application_count=cast(int, row["open_application_count"]),
            task_count=cast(int, row["task_count"]),
            completed_task_count=cast(int, row["completed_task_count"]),
            failed_task_count=cast(int, row["failed_task_count"]),
            waiting_user_count=cast(int, row["waiting_user_count"]),
            model_call_count=cast(int, row["model_call_count"]),
            consumed_tokens=int(row["consumed_tokens"]),
            consumed_seconds=cast(Decimal, row["consumed_seconds"]),
            verified_action_count=cast(int, row["verified_action_count"]),
            unconfirmed_action_count=cast(int, row["unconfirmed_action_count"]),
        )


class PostgresDashboardLoader:
    """Own a short read transaction for each independently consistent snapshot."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def __call__(self, query: DashboardQuery) -> DashboardSnapshot:
        with self.engine.connect().execution_options(
            isolation_level="REPEATABLE READ"
        ) as connection:
            with connection.begin():
                connection.exec_driver_sql("SET TRANSACTION READ ONLY")
                return DashboardRepository(connection).load(query)
